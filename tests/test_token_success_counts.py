from distrotest_lite_validation.log_success import validate_line, validate_line_v1_1


def test_skip_counts_and_durations_do_not_certify_zero_test_success():
    for line in ["Test cases: 0 passed, 5 skipped in 0.1s", "All 0 test cases passed; 12 skipped", "Tests: 0 passed in 7.2 seconds"]:
        assert validate_line(line)['positive'] is True  # retained historical behavior
        assert validate_line_v1_1(line)['positive'] is False


def test_nonzero_success_with_skips_and_custom_summary_remains_supported():
    for line in ["Test cases: 3 passed, 5 skipped in 0.1s", "All 521 test cases passed."]:
        assert validate_line_v1_1(line)['positive'] is True
