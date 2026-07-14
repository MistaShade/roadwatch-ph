import unittest

import extract_rdd
import train_model


class TrainingConfigTests(unittest.TestCase):
    def test_training_uses_five_required_countries(self) -> None:
        required = {"Japan", "India", "United_States", "Norway", "Czech"}
        self.assertGreaterEqual(len(train_model.COUNTRIES), 5)
        self.assertTrue(required.issubset(set(train_model.COUNTRIES)))

    def test_extraction_includes_the_same_training_countries(self) -> None:
        required = {"Japan", "India", "United_States", "Norway", "Czech"}
        self.assertTrue(required.issubset(set(extract_rdd.COUNTRIES.keys())))

    def test_training_uses_vgg16_with_rbf_svm(self) -> None:
        self.assertEqual(train_model.MODEL_ARCHITECTURE, "vgg16_svm")
        self.assertEqual(train_model.SVM_KERNEL, "rbf")


if __name__ == "__main__":
    unittest.main()
