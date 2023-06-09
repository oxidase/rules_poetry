def parse_lock_file(data, platforms = None):
    _MARKERS = "markers = "
    _URL = "url = "
    result = ""
    for package_lines in data.split("[[package]]"):
        section, name, version, description, files, deps, markers, url = "package", "", "", "", "", [], {}, ""
        for line in package_lines.split("\n"):
            line = line.strip()
            if line == "[package.dependencies]":
                section = "dependencies"
            elif line == "[package.source]":
                section = "source"
            elif line.startswith("["):
                section = "unknown"
            elif section == "package" and line.startswith("name = "):
                name = line.replace("name = ", "").strip('",')
            elif section == "package" and line.startswith("version = "):
                version = line.replace("version = ", "").strip('",')
            elif section == "package" and line.startswith("description = "):
                description = line
            elif section == "package" and line.startswith("{file = ") and ", hash = " in line:
                files += "\n    " + line.replace("{file = ", "").replace(", hash = ", ": ").replace("},", ",")
            elif section == "dependencies" and line and line[0].isalnum():
                dep_name, dep_version = line.split("=", 1)
                dep_name = dep_name.strip().strip('"').strip("'").replace("_", "-").replace(".", "-").lower()
                deps.append('":{}"'.format(dep_name))
                if _MARKERS in dep_version:
                    dep_marker = dep_version[dep_version.find(_MARKERS) + len(_MARKERS):]
                    for index in range(1, len(dep_marker)):
                        if dep_marker[index - 1] != "\\" and dep_marker[index] == '"':
                            markers[dep_name] = dep_marker[1:index]
                            break
            elif section == "source" and line.startswith(_URL):
                url = line[len(_URL):]

        if name:
            result += """
package_wheel(
  name = "{name}_wheel",
  constraint = "{name}=={version}",{description}
  files = {{{files}
  }},{platforms}
  visibility = [\"//visibility:public\"],
)

package(
  name = "{name}",
  wheel = ":{name}_wheel",{deps}{markers}{url}{platforms}
  visibility = [\"//visibility:public\"],
)
""".format(
                name = name,
                version = version,
                description = "\n  " + description + "," if description else "",
                files = files,
                deps = "\n  deps = [{}],".format(", ".join(deps)) if deps else "",
                markers = "\n  markers = '''{}''',".format(json.encode(markers)) if markers else "",
                url = "\n  url = {},".format(url) if url else "",
                platforms = "\n  platforms = {},".format(platforms) if platforms else "",
            )

    return result

def _poetry_venv_impl(rctx):
    rules_repository = str(rctx.path(rctx.attr._self)).split("/")[-4]
    rules_repository = ("@@" if "~" in rules_repository else "@") + rules_repository
    prefix = '''load("{name}//python:poetry_deps.bzl", "package", "package_wheel")\n'''.format(name = rules_repository)
    rctx.file("BUILD", prefix + parse_lock_file(rctx.read(rctx.attr.lock), rctx.attr.platforms))
    rctx.file("WORKSPACE")

poetry_venv = repository_rule(
    attrs = {
        "lock": attr.label(
            allow_single_file = True,
            doc = "Poetry lock file",
        ),
        "platforms": attr.string_list_dict(
            doc = "The mapping of interpter substrings to Python platform tags and environment markers as a JSON string",
        ),
        "_self": attr.label(
            allow_single_file = True,
            default = ":poetry_venv.bzl",
        ),
    },
    doc = """Process Poetry lock file.""",
    implementation = _poetry_venv_impl,
)
