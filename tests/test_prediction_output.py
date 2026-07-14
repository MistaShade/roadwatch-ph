import unittest

import predict


class PredictionOutputTests(unittest.TestCase):
    def test_build_top_predictions_returns_sorted_results(self) -> None:
        class_names = ["pothole", "alligator_crack", "longitudinal_crack", "transverse_crack"]
        probabilities = [0.55, 0.25, 0.15, 0.05]

        top_predictions = predict.build_top_predictions(class_names, probabilities, top_n=3)

        self.assertEqual(len(top_predictions), 3)
        self.assertEqual(top_predictions[0]["type"], "pothole")
        self.assertEqual(top_predictions[1]["type"], "alligator_crack")
        self.assertEqual(top_predictions[2]["type"], "longitudinal_crack")
        self.assertAlmostEqual(top_predictions[0]["confidence"], 55.0)

    def test_build_top_predictions_from_probabilities_returns_sorted_results(self) -> None:
        probabilities = {
            "pothole": 0.55,
            "alligator_crack": 0.25,
            "longitudinal_crack": 0.15,
            "transverse_crack": 0.05,
        }

        top_predictions = predict.build_top_predictions_from_probabilities(probabilities, top_n=3)

        self.assertEqual(len(top_predictions), 3)
        self.assertEqual(top_predictions[0]["type"], "pothole")
        self.assertEqual(top_predictions[1]["type"], "alligator_crack")
        self.assertEqual(top_predictions[2]["type"], "longitudinal_crack")
        self.assertAlmostEqual(top_predictions[0]["confidence"], 55.0)

    def test_select_primary_class_prefers_damage_over_intact_when_close(self) -> None:
        class_names = ["intact_road", "alligator_crack", "longitudinal_crack"]
        probabilities = [0.41, 0.39, 0.20]

        best_idx = predict.select_primary_class(class_names, probabilities)

        self.assertEqual(best_idx, 1)

    def test_resolve_orientation_bins_prefers_artifact_value(self) -> None:
        artifact = {"orientation_bins": 18}
        metadata = {}

        self.assertEqual(predict.resolve_orientation_bins(artifact, metadata), 18)


if __name__ == "__main__":
    unittest.main()
