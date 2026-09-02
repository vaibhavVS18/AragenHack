"""Pure implementations of the three MCP tools.

Kept free of MCP protocol code so they stay directly unit-testable;
server.py is the only file that registers them with the protocol.

TODO(step 2):
    get_reference_range(test_name)
    classify_lab_result(test_name, value, unit)
    route_by_severity(results)
"""
