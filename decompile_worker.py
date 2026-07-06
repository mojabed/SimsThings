import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        return 1

    source_path = Path(sys.argv[1]).resolve()
    output_path = Path(sys.argv[2]).resolve()

    try:
        from decompyle3 import decompile_file as decompile3
    except Exception:
        decompile3 = None

    try:
        from uncompyle6.main import decompile_file as decompile6
    except Exception:
        decompile6 = None

    if decompile3 is not None:
        try:
            with output_path.open("w", encoding="utf-8") as out_stream:
                decompile3(str(source_path), outstream=out_stream)
            with output_path.open("r", encoding="utf-8") as out_stream:
                content = out_stream.read().strip()
            if content and "__decompilation_failed__" not in content:
                return 0
            error_text = "decompyle3 produced no usable source"
        except Exception as exc:
            error_text = str(exc)
    else:
        error_text = "decompyle3 not available"

    if decompile6 is not None:
        try:
            with output_path.open("w", encoding="utf-8") as out_stream:
                decompile6(str(source_path), outstream=out_stream)
            with output_path.open("r", encoding="utf-8") as out_stream:
                content = out_stream.read().strip()
            if content and "__decompilation_failed__" not in content:
                return 0
            error_text = "uncompyle6 produced no usable source"
        except Exception as exc:
            error_text = str(exc)
    else:
        error_text = "uncompyle6 not available"

    with output_path.open("w", encoding="utf-8") as out_stream:
        out_stream.write(
            f"# Automatic decompilation failed for {source_path.name}\n"
            f"# Reason: {error_text}\n"
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
