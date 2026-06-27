from suite.registry import TOOLS
from suite.state import (
    render_state_export,
    render_state_import,
    render_state_sources,
)
from suite.ui import configure_page, render_suite_header, select_tool


def main() -> None:
    configure_page()
    render_suite_header()
    render_state_import()

    tool = select_tool(TOOLS)
    tool.render(tool)
    render_state_sources()
    render_state_export()


if __name__ == "__main__":
    main()
