"""Built-in screens that the TUI ships with this proposal."""

from alloy_cli.tui.screens.board_picker import BoardPickerScreen
from alloy_cli.tui.screens.build_log import BuildLogScreen
from alloy_cli.tui.screens.clock_tree import ClockTreeScreen
from alloy_cli.tui.screens.dashboard import DashboardScreen
from alloy_cli.tui.screens.flash import FlashScreen
from alloy_cli.tui.screens.onboarding import OnboardingScreen
from alloy_cli.tui.screens.peripheral_add import PeripheralAddScreen
from alloy_cli.tui.screens.welcome import WelcomeScreen

__all__ = [
    "BoardPickerScreen",
    "BuildLogScreen",
    "ClockTreeScreen",
    "DashboardScreen",
    "FlashScreen",
    "OnboardingScreen",
    "PeripheralAddScreen",
    "WelcomeScreen",
]
