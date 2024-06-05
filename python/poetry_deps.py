import argparse
import json
import logging
import os
import sys
import urllib
import warnings
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from pip._internal.commands import create_command
    from pip._internal.locations import USER_CACHE_DIR
    from pip._internal.models.direct_url import DIRECT_URL_METADATA_NAME
    from pip._vendor.packaging.utils import parse_wheel_filename
    from pip._vendor.packaging.version import InvalidVersion

_SHA256_PREFIX = "sha256:"


def get_platform_args(args):
    """Format Python platform tags and version arguments.

    Ref: https://packaging.python.org/en/latest/specifications/platform-compatibility-tags/#platform-tag
    """

    platform_args = []

    if args.platform:
        platform_args = [f"--platform={platform}" for platform in args.platform]

    if args.python_version and args.python_version != "3":
        platform_args.append(f"--python-version={args.python_version}")

    return platform_args


def install(args):
    output_path = Path(args.output)

    source_urls = []
    if args.source_url:
        # Special case for debugging
        local_package_path = Path(args.source_url[0])
        if local_package_path.is_absolute() and local_package_path.is_dir():
            # Add symbolic links to the local directory
            for item in local_package_path.iterdir():
                (output_path / item.name).symlink_to(item)
            return 0

        # Otherwise it is a list of files or URLs
        # Filter by supported platforms
        for url in args.source_url:
            try:
                wheel_name = urllib.parse.unquote(url[url.rfind("/") + 1 :], encoding="utf-8", errors="replace")
                _, _, _, tags = parse_wheel_filename(wheel_name)

                if any(tag.platform == "any" or tag.platform in args.platform for tag in tags):
                    source_urls.append(url)
            except InvalidVersion:
                source_urls.append(url)

    if len(source_urls) >= 2:
        raise RuntimeError(f"expected a single source URL but {', '.join(source_urls)} received")

    # Install wheel
    install_command = create_command("install")

    package_files = json.loads(args.files) if args.files else {}
    requirements_file = output_path / "requirements.txt"
    with requirements_file.open("wt") as requirements_fileobj:
        if args.index:
            requirements_fileobj.write("".join([f"--extra-index-url={index}\n" for index in args.index]))

        requirements_lines = []
        requirements_lines += source_urls if source_urls else [args.input]
        requirements_lines += [f" --hash={value}" for value in package_files.values()]
        requirements_fileobj.write(" \\\n".join(requirements_lines))

    install_args = [
        "-r",
        os.fspath(requirements_file),
    ]

    try:
        possible_cache = Path(USER_CACHE_DIR)
        use_cache = os.access(possible_cache, os.W_OK)
    except (PermissionError, OSError):
        use_cache = False

    install_args.append(f"--cache-dir={possible_cache}" if use_cache else "--no-cache-dir")

    install_args += [
        f"--target={output_path}",
        "--prefer-binary",
        "--no-compile",
        "--no-dependencies",
        "--disable-pip-version-check",
        "--use-pep517",
        "--quiet",
    ]

    if args.cc_toolchain is not None:
        cc = json.loads(args.cc_toolchain)
        os.environ.update({k[1:]: v for k, v in cc.items() if k[0] == " "})
        os.environ.update({k[1:]: os.fspath(Path(v).resolve()) for k, v in cc.items() if k[0] == "~"})

    if retcode := install_command.main(install_args + get_platform_args(args)):
        logging.error(f"pip install returned {retcode}")
        return retcode

    # Clean-up some metadata files which may contain non-hermetic data
    for direct_url_path in output_path.glob(f"*.dist-info/{DIRECT_URL_METADATA_NAME}"):
        direct_url_path.unlink()
        record_path = direct_url_path.parent / "RECORD"
        if record_path.exists():
            direct_url_line = f"{direct_url_path.relative_to(output_path)},"
            with open(record_path) as record_file:
                records = record_file.readlines()
            with open(record_path, "wt") as record_file:
                record_file.writelines(record for record in records if not record.startswith(direct_url_line))

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and install a Poetry package")
    subparsers = parser.add_subparsers(required=True)

    parser_install = subparsers.add_parser("install")
    parser_install.set_defaults(func=install)
    parser_install.add_argument("input", type=str, help="wheel version constraint")
    parser_install.add_argument("output", type=Path, default=Path(), help="package output directory")
    parser_install.add_argument("--files", type=str, default="{}", help="files:hash  dictionary")
    parser_install.add_argument("--python_version", type=str, default=None, help="python version")
    parser_install.add_argument("--platform", type=str, nargs="*", action="extend", help="platform tag")
    parser_install.add_argument("--index", type=str, nargs="*", action="extend", help="index URL")
    parser_install.add_argument("--source_url", type=str, nargs="*", action="extend", help="source URLs")
    parser_install.add_argument("--cc_toolchain", type=str, help="CC toolchain")

    args = parser.parse_args()
    sys.exit(args.func(args))
