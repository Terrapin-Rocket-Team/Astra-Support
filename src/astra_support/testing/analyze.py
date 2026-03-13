from __future__ import annotations

STATUS_PASS = "PASS"
STATUS_TEST_FAIL = "TEST_FAIL"
STATUS_COMPILE_ERR = "COMPILE_ERR"
STATUS_SYSTEM_ERR = "SYSTEM_ERR"


def analyze_output(log_text: str, return_code: int) -> tuple[str, str]:
    lines = log_text.splitlines()
    cleaned_lines: list[str] = []
    found_assert_fail = False
    found_syntax_error = False
    found_system_lock = False
    found_pio_error = False

    for line in lines:
        line_strip = line.strip()
        is_unity_fail = ":FAIL:" in line or ("[FAILED]" in line and (".cpp:" in line or ".c:" in line))
        if is_unity_fail:
            cleaned_lines.append(line_strip)
            found_assert_fail = True
        elif ": error:" in line or "undefined reference" in line or "fatal error:" in line:
            cleaned_lines.append(line_strip)
            found_syntax_error = True
        elif "Error:" in line or "ERROR:" in line:
            cleaned_lines.append(line_strip)
            found_pio_error = True
        elif "Permission denied" in line or "cannot open output file" in line or "Device or resource busy" in line:
            cleaned_lines.append(line_strip)
            found_system_lock = True

    if return_code == 0:
        if found_assert_fail:
            return STATUS_TEST_FAIL, "\n".join(cleaned_lines)
        return STATUS_PASS, ""
    if found_assert_fail:
        return STATUS_TEST_FAIL, "\n".join(cleaned_lines)
    if found_system_lock or found_pio_error:
        return STATUS_SYSTEM_ERR, "\n".join(cleaned_lines)
    if found_syntax_error:
        return STATUS_COMPILE_ERR, "\n".join(cleaned_lines)
    if not cleaned_lines:
        cleaned_lines = ["No error output captured."]
    return STATUS_SYSTEM_ERR, "\n".join(cleaned_lines)


def parse_test_counts(log_text: str) -> tuple[int | None, int | None, int | None]:
    total = None
    passed = None
    failed = None
    collected = None
    for line in log_text.splitlines():
        line_strip = line.strip()
        if line_strip.startswith("Collected ") and " tests" in line_strip:
            parts = line_strip.split()
            if len(parts) >= 2 and parts[1].isdigit():
                collected = int(parts[1])
        if " test cases:" in line_strip and ("failed" in line_strip or "succeeded" in line_strip):
            left, right = line_strip.split(" test cases:", 1)
            digits = "".join(ch for ch in left if ch.isdigit())
            total = int(digits) if digits else None
            passed = 0
            failed = 0
            for part in right.split(","):
                item = part.strip()
                if "failed" in item:
                    try:
                        failed = int(item.split()[0])
                    except ValueError:
                        pass
                if "succeeded" in item:
                    try:
                        passed = int(item.split()[0])
                    except ValueError:
                        pass
            break
    if total is None:
        total = collected
    return total, passed, failed
