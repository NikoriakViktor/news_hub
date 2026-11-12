"""Ті самі перевірки в стилі unittest: pytest запускає і їх."""
import unittest

from newsapp.text import reading_time


class ReadingTimeTest(unittest.TestCase):
    def setUp(self) -> None:                 # перед кожним тестом — як фікстура
        self.text = "слово " * 201

    def test_rounds_up(self) -> None:
        self.assertEqual(reading_time(self.text), 2)

    def test_wpm_must_be_positive(self) -> None:
        with self.assertRaises(ValueError):
            reading_time(self.text, wpm=-1)
