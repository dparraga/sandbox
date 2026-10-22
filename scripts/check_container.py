"""Verify bootstrap-only container behavior with restricted offline runtime."""

import argparse
import subprocess


def run(command, expected=0):
    result = subprocess.run(command, text=True, capture_output=True, timeout=60, check=False)
    print(result.stdout, end="")
    print(result.stderr, end="")
    if result.returncode != expected:
        raise RuntimeError(f"Expected exit {expected}, received {result.returncode}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    args = parser.parse_args()
    restricted = ["docker", "run", "--rm", "--network", "none", "--read-only", "--cap-drop", "ALL",
                  "--security-opt", "no-new-privileges"]
    for options, expected in [([], 0), (["--help"], 0), (["--version"], 0), (["--invalid-option"], 2)]:
        result = run(restricted + [args.image] + options, expected)
        if expected == 2:
            assert not result.stdout and "unrecognized arguments" in result.stderr
        else:
            assert not result.stderr
            if not options:
                assert "bootstrap" in result.stdout.lower() and "unavailable" in result.stdout.lower()
            elif options == ["--version"]:
                assert result.stdout.strip() == "flex-photo 0.1.0"
            else:
                assert "--version" in result.stdout
    # This also records the actual container interpreter and verifies numeric nonroot execution.
    run(restricted + ["--entrypoint", "python", args.image, "-c",
                      "import os,sys,importlib.util; assert os.getuid()!=0; "
                      "assert importlib.util.find_spec('setuptools') is None; "
                      "print(sys.version); print('uid:',os.getuid())"])


if __name__ == "__main__":
    main()
