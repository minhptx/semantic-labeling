#!/usr/bin/python
# -*- coding: utf-8 -*-

from typing import Dict, Tuple, List, Union, Optional, Set, Iterable

from pathlib import Path

from pyutils.list_utils import _
from sklearn import preprocessing
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression

from semantic_labeling.column import Column
from semantic_labeling.generate_train_data import generate_training_data
from semantic_labeling.sm_type_db import SemanticTypeDB
from semantic_modeling.config import get_logger, config
from semantic_modeling.data_io import get_cache_dir
from semantic_modeling.karma.semantic_model import SemanticModel, SemanticType
from semantic_modeling.utilities.serializable import deserialize, serialize


class SemanticTyper(object):

    logger = get_logger("app.semantic_labeling.typer")
    instance = None

    def __init__(self,
                 dataset: str,
                 train_sms: List[SemanticModel],
                 exec_dir: Optional[Path] = None) -> None:
        self.dataset = dataset
        self.train_source_ids = {sm.id for sm in train_sms}
        if exec_dir is None:
            exec_dir = get_cache_dir(dataset, train_sms) / "semantic-labeling"
        self.exec_dir = Path(exec_dir)
        self.exec_dir.mkdir(exist_ok=True, parents=True)

        self.model = None
        self.preprocessor = None
        self.stype_db = SemanticTypeDB.get_stype_db(dataset, [sm.id for sm in train_sms], self.exec_dir)

    def load_model(self):
        """Try to load previous model if possible"""
        if self.model is not None:
            return

        model_file = self.exec_dir / 'model.pkl'
        if model_file.exists():
            self.logger.debug("Load previous trained model...")
            self.model = deserialize(model_file)
        else:
            self.logger.error("Cannot load model...")
            raise Exception("Model doesn't exist..")

    @staticmethod
    def get_instance(dataset: str,
                     train_sms: List[SemanticModel],
                     exec_dir: Optional[Path] = None) -> 'SemanticTyper':
        if SemanticTyper.instance is None:
            SemanticTyper.instance = SemanticTyper(dataset, train_sms, exec_dir)

        assert SemanticTyper.instance.dataset == dataset and \
               SemanticTyper.instance.train_source_ids == {sm.id for sm in train_sms}

        return SemanticTyper.instance

    def semantic_labeling(self,
                          train_sources: List[SemanticModel],
                          test_sources: List[SemanticModel],
                          top_n: int,
                          eval_train: bool = False) -> None:
        """Generate semantic labels and store it in test sources"""
        train_sources: Dict[str, SemanticModel] = {s.id: s for s in train_sources}
        test_sources: Dict[str, SemanticModel] = {s.id: s for s in test_sources}
        assert set(train_sources.keys()) == self.train_source_ids

        if self.model is None:
            model_file = self.exec_dir / 'model.pkl'
            preprocessor_file = self.exec_dir / 'preprocessor.pkl'

            if model_file.exists():
                self.logger.debug("Load previous trained model...")
                self.model = deserialize(model_file)
                self.preprocessor = deserialize(preprocessor_file)
                print(self.model.coef_)
            else:
                self.logger.debug("Train new model...")
                x_train, y_train, x_test, y_test = generate_training_data(self.stype_db)
                preprocessor = preprocessing.StandardScaler()
                preprocessor.fit_transform(x_train)
                # clf = LogisticRegression(class_weight="balanced")
                # clf = RandomForestClassifier(n_estimators=200, max_depth=10, class_weight="balanced", random_state=120)
                clf = LogisticRegression()
                clf = clf.fit(x_train, y_train)
                self.logger.debug("Save model...")
                serialize(clf, model_file)
                serialize(preprocessor, preprocessor_file)
                self.model = clf
                self.preprocessor = preprocessor

        col_attrs = []
        if eval_train:
            for col in self.stype_db.train_columns:
                if col.table_name not in train_sources: continue
                col_attrs.append((col, train_sources[col.table_name].get_attr_by_label(col.name)))

        for col in self.stype_db.test_columns:
            if col.table_name not in test_sources: continue
            col_attrs.append((col, test_sources[col.table_name].get_attr_by_label(col.name)))

        for col, attr in col_attrs:
            pred_stypes = self.pred_type(col, top_n)
            attr.semantic_types = [
                SemanticType(stype[0].decode("utf-8"), stype[1].decode("utf-8"), score)
                for stype, score in pred_stypes if score > 0
            ]

    def pred_type(self, col: Column, top_n: int) -> List[Tuple[Tuple[bytes, bytes], float]]:
        X = []
        refcols = [refcol for refcol in self.stype_db.train_columns if refcol.id != col.id]
        j = self.stype_db.col2idx[col.id]
        if col.id == "s5_Category_Page_Box_Content:Image":
            for refcol in refcols:
                iref = self.stype_db.col2idx[refcol.id]
                print(refcol.id, self.stype_db.similarity_matrix[j, iref])

        for refcol in refcols:
            iref = self.stype_db.col2idx[refcol.id]
            X.append(self.stype_db.similarity_matrix[j, iref])

        X = self.preprocessor.transform(X)
        result = self.model.predict_proba(X)[:, 1]
        result = _(zip(result, (self.stype_db.col2types[rc.id] for rc in refcols))) \
            .sort(key=lambda x: x[0], reverse=True)
        top_k_st = {}
        for score, stype in result:
            if stype not in top_k_st:
                top_k_st[stype] = score
                if len(top_k_st) == top_n:
                    break

        return sorted([(stype, score) for stype, score in top_k_st.items()], reverse=True, key=lambda x: x[1])


