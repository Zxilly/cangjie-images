from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from cangjie_images.config import DEFAULT_IMAGE_NAME
from cangjie_images.planner import (
    build_plan,
    merge_release_manifests,
    write_digest_metadata,
    write_github_outputs,
    write_summary,
)

if TYPE_CHECKING:
    from cangjie_images.generator import GenerationResult

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None


def _env_str(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan and publish Cangjie Docker images.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Generate a publish plan.")
    plan_parser.add_argument("--image", default=DEFAULT_IMAGE_NAME, help="Docker image name.")
    plan_parser.add_argument(
        "--versions-root",
        type=Path,
        default=Path("versions"),
        help="Directory containing committed Dockerfiles (defaults to ./versions).",
    )
    plan_parser.add_argument(
        "--nightly-context-root",
        type=Path,
        default=Path("build-context"),
        help="Directory where nightly Dockerfiles are rendered (defaults to ./build-context).",
    )
    plan_parser.add_argument(
        "--include-nightly",
        action="store_true",
        default=_env_bool("CANGJIE_INCLUDE_NIGHTLY"),
        help="Include the latest nightly release if the API token is configured. "
        "Also enabled when CANGJIE_INCLUDE_NIGHTLY is truthy.",
    )
    plan_parser.add_argument(
        "--force",
        action="store_true",
        default=_env_bool("CANGJIE_FORCE"),
        help="Publish every generated release, even if all tags already exist. "
        "Also enabled when CANGJIE_FORCE is truthy.",
    )
    plan_parser.add_argument(
        "--github-output",
        type=Path,
        default=_env_path("GITHUB_OUTPUT"),
        help="Write GitHub Actions outputs to this path (defaults to $GITHUB_OUTPUT).",
    )
    plan_parser.add_argument(
        "--summary",
        type=Path,
        default=_env_path("GITHUB_STEP_SUMMARY"),
        help="Write a markdown summary to this path (defaults to $GITHUB_STEP_SUMMARY).",
    )

    gen_parser = subparsers.add_parser(
        "generate",
        help="Render committed Dockerfiles for stable releases into versions/<channel>/<version>/<base>/Dockerfile.",
    )
    gen_parser.add_argument(
        "--versions-root",
        type=Path,
        default=Path("versions"),
        help="Directory to write Dockerfiles into (defaults to ./versions).",
    )
    gen_parser.add_argument(
        "--force",
        action="store_true",
        default=_env_bool("CANGJIE_GENERATE_FORCE"),
        help="Overwrite every committed Dockerfile. Also enabled via CANGJIE_GENERATE_FORCE.",
    )
    gen_parser.add_argument(
        "--force-version",
        default=_env_str("CANGJIE_GENERATE_FORCE_VERSION"),
        help="Overwrite Dockerfiles for a single version (e.g. 1.0.5). "
        "Also settable via CANGJIE_GENERATE_FORCE_VERSION.",
    )
    gen_parser.add_argument(
        "--skip-smoke-test",
        action="store_true",
        help="Skip running cjc/cjpm --version on the captured SDK. Required on runners that "
        "cannot execute the reference arch (e.g. arm64-only hosts).",
    )
    gen_parser.add_argument(
        "--summary",
        type=Path,
        default=_env_path("GITHUB_STEP_SUMMARY"),
        help="Append a markdown summary to this path (defaults to $GITHUB_STEP_SUMMARY).",
    )

    digest_parser = subparsers.add_parser(
        "write-digest",
        help="Write digest metadata for a build job artifact.",
    )
    digest_parser.add_argument("--output-dir", type=Path, required=True)
    digest_parser.add_argument("--release-id", required=True)
    digest_parser.add_argument("--arch", required=True)
    digest_parser.add_argument("--digest", required=True)

    merge_parser = subparsers.add_parser(
        "merge",
        help="Create a multi-arch manifest from uploaded digests.",
    )
    merge_parser.add_argument("--image", default=DEFAULT_IMAGE_NAME, help="Docker image name.")
    merge_parser.add_argument("--release-id", required=True)
    merge_parser.add_argument("--tags-json", required=True)
    merge_parser.add_argument("--arches-json", required=True)
    merge_parser.add_argument("--digests-dir", type=Path, required=True)
    merge_parser.add_argument(
        "--summary",
        type=Path,
        default=_env_path("GITHUB_STEP_SUMMARY"),
        help="Append a markdown summary to this path (defaults to $GITHUB_STEP_SUMMARY).",
    )

    return parser


def _parse_string_array(raw: str, option: str, parser: argparse.ArgumentParser) -> list[str]:
    value = json.loads(raw)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        parser.error(f"{option} must be a JSON array of strings")
    return value  # type: ignore[return-value]


def _write_generate_summary(
    result: GenerationResult,
    summary_path: Path,
    *,
    force: bool,
    force_version: str | None,
) -> None:
    lines = [
        "## Cangjie Dockerfile Generation",
        "",
        f"- Force: `{force}`",
        f"- Force version: `{force_version or '-'}`",
        f"- Written: `{len(result.written)}`",
        f"- Skipped (existing): `{len(result.skipped_existing)}`",
        f"- Skipped (no sources): `{len(result.skipped_no_sources)}`",
    ]
    if result.written:
        lines.extend(["", "### Written", ""])
        for entry in result.written:
            lines.append(
                f"- `{entry.channel}/{entry.version}/{entry.base}/{entry.arch}` → `{entry.path}`"
            )
    with summary_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "plan":
        plan = build_plan(
            image_name=args.image,
            include_nightly=args.include_nightly,
            force=args.force,
            versions_root=args.versions_root,
            nightly_context_root=args.nightly_context_root,
        )
        if args.github_output:
            write_github_outputs(plan, args.github_output)
        if args.summary:
            write_summary(plan, args.summary)
        if args.github_output or args.summary:
            print(
                f"Prepared {len(plan.publish_matrix)} release variants "
                f"and {len(plan.build_matrix)} platform builds."
            )
        else:
            print(plan.as_json())
        return 0

    if args.command == "generate":
        from cangjie_images.generator import generate

        force_version = args.force_version.strip() if args.force_version else None
        result = generate(
            versions_root=args.versions_root,
            force=args.force,
            force_version=force_version or None,
            run_smoke_test=not args.skip_smoke_test,
        )
        if args.summary:
            _write_generate_summary(
                result, args.summary, force=args.force, force_version=force_version
            )
        print(
            f"Wrote {len(result.written)} Dockerfiles; "
            f"skipped {len(result.skipped_existing)} existing, "
            f"{len(result.skipped_no_sources)} missing sources."
        )
        return 0

    if args.command == "write-digest":
        path = write_digest_metadata(
            output_dir=args.output_dir,
            release_id=args.release_id,
            arch=args.arch,
            digest=args.digest,
        )
        print(path)
        return 0

    if args.command == "merge":
        tags = _parse_string_array(args.tags_json, "--tags-json", parser)
        arches = _parse_string_array(args.arches_json, "--arches-json", parser)
        merge_release_manifests(
            image_name=args.image,
            release_id=args.release_id,
            tags=tags,
            arches=arches,
            digests_dir=args.digests_dir,
            summary_path=args.summary,
        )
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2
