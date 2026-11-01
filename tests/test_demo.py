"""Menu actions must run only what the user selects."""

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.demo import menu


class TestDemoMenu(unittest.TestCase):
    def test_exit_does_not_start_experiment(self):
        with patch('builtins.input', return_value='0'), patch('builtins.print'), \
                patch('scripts.demo.run_benchmark') as run:
            menu()
            run.assert_not_called()

    def test_select_baseline_does_not_run_plots(self):
        with patch('builtins.input', side_effect=['2', '0']), patch('builtins.print'), \
                patch('scripts.demo.run_benchmark', return_value=Path('/tmp/results')) as run, \
                patch('scripts.demo.make_plots') as plots:
            menu()
            run.assert_called_once_with(duration=60, scenario='baseline')
            plots.assert_not_called()

    def test_invalid_duration_keeps_previous_setting(self):
        with patch('builtins.input', side_effect=['7', 'nan', '4', '0']), patch('builtins.print'), \
                patch('scripts.demo.run_benchmark') as run:
            menu()
            run.assert_called_once_with(duration=60, scenario='both')
