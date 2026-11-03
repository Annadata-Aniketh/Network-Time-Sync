"""Menu actions must run only what the user selects."""

import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.demo import menu


class TestDemoMenu(unittest.TestCase):
    def setUp(self):
        # Test the selected mode explicitly, independently of the test runner's TTY.
        terminal_patch = patch('scripts.demo.Terminal', autospec=True)
        self.terminal = terminal_patch.start().return_value
        self.addCleanup(terminal_patch.stop)
        self.terminal.interactive = False

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

    def test_recovery_menu_choice(self):
        with patch('builtins.input', side_effect=['9', '0']), patch('builtins.print'), \
                patch('scripts.demo.run_benchmark') as run:
            menu()
            run.assert_called_once_with(duration=60, scenario='recovery')

    def test_scenario_dispatch_in_interactive_and_plain_modes(self):
        for interactive in [False, True]:
            for choice, scenario in [('2', 'baseline'), ('3', 'optimized'),
                                     ('4', 'both'), ('9', 'recovery')]:
                with self.subTest(interactive=interactive, scenario=scenario):
                    self.terminal.interactive = interactive
                    directory = Path('/tmp/results')
                    with patch('builtins.input', side_effect=[choice, '0']), \
                            patch('scripts.demo.run_benchmark', return_value=directory) as run, \
                            patch('scripts.demo.make_plots') as plots, \
                            patch('scripts.demo.show_summary') as summary:
                        menu()
                        expected = dict(duration=60, scenario=scenario)
                        if interactive:
                            expected['observer'] = self.terminal.on_event
                        run.assert_called_once_with(**expected)
                        plots.assert_not_called()
                        if interactive and scenario == 'recovery':
                            summary.assert_called_once_with(directory, self.terminal)
                        else:
                            summary.assert_not_called()
