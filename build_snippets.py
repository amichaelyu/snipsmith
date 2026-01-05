"""
snippet compiler for obsidian latex suite and vscode hypersnips.

compiles snippets from a single yaml source of truth (snippets.yaml) into
platform-specific formats for obsidian and vscode/cursor. supports regex and
plaintext triggers, platform-specific overrides, shared variables, and
automatic handling of edge cases (like spaces in triggers for vscode).
"""

from typing import Dict, List, Any, Optional
import yaml
import json
import re
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv


def build_obsidian_snippets(
    snippets: List[Dict[str, Any]],
    verbatim_snippets: Dict[str, List[str]],
    output_path: Path
) -> None:
    """
    build the obsidian_snippets.js file from the snippets data.

    args:
        snippets: list of snippet definitions
        verbatim_snippets: platform-specific verbatim snippets to append
        output_path: path where the output file should be written
    """
    obsidian_snippets_data = []

    for snippet in snippets:
        # Skip snippets not targeted for Obsidian
        target_platforms = snippet.get('target_platforms')
        if target_platforms and 'obsidian' not in target_platforms:
            continue

        # Apply platform-specific overrides
        obsidian_override = snippet.get('platforms', {}).get('obsidian', {})
        final_snippet = {**snippet, **obsidian_override}

        # Deep merge options
        options = {**snippet.get('options', {}), **obsidian_override.get('options', {})}
        final_snippet['options'] = options

        # build options string for obsidian
        opts_str = ""
        # regex flag - snippets are plaintext by default unless explicitly set to true
        if final_snippet.get('regex', False):
            opts_str += 'r'
        if options.get('math'):
            opts_str += 'm'
        if options.get('inline_math'):
            opts_str += 'n'
        if options.get('display_math'):
            opts_str += 'M'
        if options.get('text'):
            opts_str += 't'
        if options.get('code'):
            opts_str += 'c'
        if options.get('auto'):
            opts_str += 'A'
        if options.get('visual'):
            opts_str += 'v'
        if options.get('word_boundary'):
            opts_str += 'w'
        final_snippet['options_str'] = opts_str

        # Handle {{VAR}} syntax for obsidian native variables
        final_snippet['trigger'] = re.sub(r'\{\{(\w+)\}\}', r'${\1}', final_snippet['trigger'])

        obsidian_snippets_data.append(final_snippet)

    # generate the file content for obsidian
    output_lines = []
    for s in obsidian_snippets_data:
        # for regex triggers, wrap in slashes; for plaintext, use string format
        is_regex = s.get('regex', False)
        if is_regex:
            trigger_str = f"trigger: /{s['trigger']}/"
        else:
            trigger_str = f"trigger: {json.dumps(s['trigger'])}"

        replacement_str = json.dumps(s['replacement'])
        options_str = json.dumps(s['options_str'])
        description_str = json.dumps(s.get('description', ''))

        line_parts = [
            trigger_str,
            f"replacement: {replacement_str}",
            f"options: {options_str}",
            f"description: {description_str}"
        ]

        if 'priority' in s:
            line_parts.append(f"priority: {s['priority']}")

        line = f"    {{ {', '.join(line_parts)} }}"
        output_lines.append(line)

    file_content = "[\n" + ",\n".join(output_lines)

    # Append verbatim snippets if any
    if verbatim_snippets.get('obsidian'):
        file_content += ",\n"
        verbatim_lines = [f"    {s.strip()}" for s in verbatim_snippets['obsidian']]
        file_content += ",\n".join(verbatim_lines)

    file_content += "\n]\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(file_content, encoding='utf-8')
    print(f"✓ Built {output_path}")


def build_obsidian_variables(variables: Dict[str, str], output_path: Path) -> None:
    """
    build the obsidian_variables.json file from the variables data.

    args:
        variables: dictionary of variable names to values
        output_path: path where the output file should be written
    """
    obsidian_vars = {f"${{{key}}}": value for key, value in variables.items()}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(obsidian_vars, indent=4), encoding='utf-8')
    print(f"✓ Built {output_path}")


def build_latex_snippets(
    snippets: List[Dict[str, Any]],
    variables: Dict[str, str],
    verbatim_snippets: Dict[str, List[str]],
    output_path: Path
) -> None:
    """
    build the latex.hsnips file from the snippets data.

    args:
        snippets: list of snippet definitions
        variables: dictionary of variable names to values
        verbatim_snippets: platform-specific verbatim snippets to append
        output_path: path where the output file should be written
    """
    hsnips_content = (
        "global\n"
        "function math(context) {\n"
        "    return context.scopes.findLastIndex(s => s.startsWith(\"meta.math\")) > "
        "context.scopes.findLastIndex(s => s.startsWith(\"comment\") || s.startsWith(\"meta.text.normal.tex\"));\n"
        "}\n"
        "function notmath(context) {\n"
        "    return context.scopes.findLastIndex(s => s.startsWith(\"meta.math\")) <= "
        "context.scopes.findLastIndex(s => s.startsWith(\"comment\") || s.startsWith(\"meta.text.normal.tex\"));\n"
        "}\n"
        "endglobal\n\n"
    )

    for snippet in snippets:
        # Skip snippets not targeted for VSCode
        target_platforms = snippet.get('target_platforms')
        if target_platforms and 'vscode' not in target_platforms:
            continue

        # Apply platform-specific overrides
        vscode_override = snippet.get('platforms', {}).get('vscode', {})
        final_snippet = {**snippet, **vscode_override}

        # Deep merge options
        options = {**snippet.get('options', {}), **vscode_override.get('options', {})}
        final_snippet['options'] = options

        # Substitute variables in trigger
        trigger = final_snippet['trigger']
        for var, val in variables.items():
            trigger = trigger.replace(f"{{{{{var}}}}}", val)

        # For hsnips, backslash is a special character in the body
        replacement = final_snippet['replacement'].replace('\\', '\\\\')
        description = final_snippet.get('description', '')

        # build flags for vscode
        flags = ""
        if options.get('auto'):
            flags += 'A'
        # default in_word to true for better ux (allows xsr → x^{2})
        if options.get('in_word', True):
            flags += 'i'
        if options.get('word_boundary'):
            flags += 'w'
        if options.get('beginning_of_line'):
            flags += 'b'
        if options.get('multi_line'):
            flags += 'M'

        # Build context
        context = ""
        if options.get('math'):
            context = "context math(context)\n"
        elif options.get('text'):
            context = "context notmath(context)\n"

        # Build snippet string
        snippet_str = ""
        if 'priority' in final_snippet:
            snippet_str += f"priority {final_snippet['priority']}\n"

        if context:
            snippet_str += context

        # determine if trigger is regex or plaintext
        # by default, snippets are plaintext (safer default)
        is_regex = final_snippet.get('regex', False)

        # vscode/hsnips doesn't support spaces in plaintext triggers
        # so we convert plaintext triggers with spaces to escaped regex
        if not is_regex and ' ' in trigger:
            trigger = re.escape(trigger)
            is_regex = True  # treat as regex for vscode only

        if is_regex:
            # regex triggers use backticks
            snippet_str += f'snippet `{trigger}` "{description}" {flags}\n'
        else:
            # plaintext triggers are unquoted
            snippet_str += f'snippet {trigger} "{description}" {flags}\n'

        snippet_str += f'{replacement}\n'
        snippet_str += 'endsnippet\n\n'

        hsnips_content += snippet_str

    # Append verbatim snippets if any
    if verbatim_snippets.get('vscode'):
        for s in verbatim_snippets['vscode']:
            hsnips_content += f"{s.strip()}\n\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(hsnips_content, encoding='utf-8')
    print(f"✓ Built {output_path}")


def resolve_path(path: str) -> Path:
    """
    resolve a path, expanding ~ and making it absolute.

    args:
        path: path string to resolve

    returns:
        resolved path object
    """
    return Path(path).expanduser().resolve()


def parse_paths_list(env_value: Optional[str]) -> List[Path]:
    """
    parse comma-separated paths from environment variable.

    args:
        env_value: comma-separated string of paths

    returns:
        list of resolved path objects
    """
    if not env_value:
        return []
    return [resolve_path(p.strip()) for p in env_value.split(',') if p.strip()]


def clean_files(paths: List[Path]) -> None:
    """
    delete the files at the given paths.

    args:
        paths: list of file paths to remove
    """
    print(">>> Cleaning up generated files...")
    for path in paths:
        try:
            path.unlink()
            print(f"    ✓ Removed {path}")
        except FileNotFoundError:
            print(f"    - Not found, skipping: {path}")
        except Exception as e:
            print(f"    ✗ Error removing {path}: {e}")


def main() -> None:
    """main entry point for the snippet builder."""
    parser = argparse.ArgumentParser(description="Build or clean snippet files.")
    parser.add_argument('--clean', action='store_true', help='Remove generated snippet files.')
    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Parse output paths
    obsidian_path = resolve_path(
        os.getenv('OBSIDIAN_SNIPPETS_PATH', 'obsidian_snippets.js')
    )
    obsidian_vars_path = resolve_path(
        os.getenv('OBSIDIAN_VARIABLES_PATH', 'obsidian_variables.json')
    )

    # Support both old single path and new comma-separated list for VSCode
    latex_paths_env = os.getenv('LATEX_SNIPPETS_PATHS') or os.getenv('LATEX_SNIPPETS_PATH')
    latex_paths = parse_paths_list(latex_paths_env)

    # Fallback to default if no paths specified
    if not latex_paths:
        latex_paths = [resolve_path('latex.hsnips')]

    # Collect all output paths for cleaning
    output_paths = [obsidian_path, obsidian_vars_path] + latex_paths

    if args.clean:
        clean_files(output_paths)
        return

    # Load snippets configuration
    snippets_file = Path("snippets.yaml")
    if not snippets_file.exists():
        print(f"✗ Error: {snippets_file} not found")
        return

    with snippets_file.open("r", encoding='utf-8') as f:
        data = yaml.safe_load(f)
        snippets = data.get('snippets', [])
        variables = data.get('variables', {})
        verbatim_snippets = data.get('verbatim_snippets', {})

    # Build Obsidian files
    build_obsidian_snippets(snippets, verbatim_snippets, obsidian_path)
    build_obsidian_variables(variables, obsidian_vars_path)

    # Build LaTeX/VSCode files for all specified paths
    for latex_path in latex_paths:
        build_latex_snippets(snippets, variables, verbatim_snippets, latex_path)

    print("\n✓ Snippet build process completed successfully!")


if __name__ == "__main__":
    main()
