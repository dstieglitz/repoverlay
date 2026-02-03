"""Colored output utilities for repoverlay."""

import os
import sys
from typing import TextIO


class Output:
    """Handles colored and formatted output."""

    # ANSI color codes
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"

    def __init__(
        self,
        *,
        no_color: bool = False,
        quiet: bool = False,
        stream: TextIO | None = None,
        err_stream: TextIO | None = None,
    ):
        """Initialize output handler.

        Args:
            no_color: Disable colored output
            quiet: Suppress informational output
            stream: Output stream (default stdout)
            err_stream: Error stream (default stderr)
        """
        self.stream = stream or sys.stdout
        self.err_stream = err_stream or sys.stderr
        self.quiet = quiet

        # Determine if color should be used
        self._use_color = self._should_use_color(no_color)

    def _should_use_color(self, no_color: bool) -> bool:
        """Determine if colored output should be used.

        Args:
            no_color: Explicit flag to disable color

        Returns:
            True if color should be used
        """
        # Explicit flag
        if no_color:
            return False

        # NO_COLOR environment variable
        if os.environ.get("NO_COLOR"):
            return False

        # Check if stdout is a TTY
        if not hasattr(self.stream, "isatty") or not self.stream.isatty():
            return False

        return True

    def _colorize(self, text: str, *codes: str) -> str:
        """Apply color codes to text.

        Args:
            text: Text to colorize
            codes: ANSI codes to apply

        Returns:
            Colorized text (or plain text if color disabled)
        """
        if not self._use_color:
            return text
        return f"{''.join(codes)}{text}{self.RESET}"

    def success(self, message: str) -> None:
        """Print a success message (green).

        Args:
            message: Message to print
        """
        if self.quiet:
            return
        print(self._colorize(message, self.GREEN), file=self.stream)

    def warning(self, message: str) -> None:
        """Print a warning message (yellow).

        Args:
            message: Message to print
        """
        print(self._colorize(f"Warning: {message}", self.YELLOW), file=self.err_stream)

    def error(self, message: str) -> None:
        """Print an error message (red).

        Args:
            message: Message to print
        """
        print(self._colorize(f"Error: {message}", self.RED), file=self.err_stream)

    def info(self, message: str) -> None:
        """Print an informational message.

        Args:
            message: Message to print
        """
        if self.quiet:
            return
        print(message, file=self.stream)

    def path(self, path: str) -> str:
        """Format a path with color (cyan).

        Args:
            path: Path to format

        Returns:
            Formatted path string
        """
        return self._colorize(path, self.CYAN)

    def header(self, text: str) -> None:
        """Print a header (bold).

        Args:
            text: Header text
        """
        if self.quiet:
            return
        print(self._colorize(text, self.BOLD), file=self.stream)

    def created(self, path: str) -> None:
        """Print a 'created' message for a path.

        Args:
            path: Path that was created
        """
        if self.quiet:
            return
        print(f"  {self._colorize('+', self.GREEN)} {self.path(path)}", file=self.stream)

    def removed(self, path: str) -> None:
        """Print a 'removed' message for a path.

        Args:
            path: Path that was removed
        """
        if self.quiet:
            return
        print(f"  {self._colorize('-', self.RED)} {self.path(path)}", file=self.stream)

    def dry_run_prefix(self) -> str:
        """Get prefix for dry-run messages.

        Returns:
            Formatted dry-run prefix
        """
        return self._colorize("[dry-run]", self.YELLOW)


# Global default output instance
_default_output: Output | None = None


def get_output() -> Output:
    """Get the default output instance.

    Returns:
        Default Output instance
    """
    global _default_output
    if _default_output is None:
        _default_output = Output()
    return _default_output


def set_output(output: Output) -> None:
    """Set the default output instance.

    Args:
        output: Output instance to use as default
    """
    global _default_output
    _default_output = output
