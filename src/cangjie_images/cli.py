from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cangjie_images.config import DEFAULT_IMAGE_NAME
from cangjie_images.planner import (
    build_plan,
    merge_release_manifests,
    write_digest_metadata,
    write_github_outputs,
    write_summary,
)
from cangjie_images.prepare import prepare_build_context


_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value) if value else None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan and publish Cangjie Docker images.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan", help="Generate a publish plan.")
    plan_parser.add_argument("--image", default=DEFAULT_IMAGE_NAME, help="Docker image name.")
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

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Download the SDK, capture envsetup.sh, and render a Dockerfile.",
    )
    prepare_parser.add_argument("--archive-url", required=True)
    prepare_parser.add_argument("--archive-sha256", default="")
    prepare_parser.add_argument("--base-image", required=True)
    prepare_parser.add_argument("--base-family", required=True)
    prepare_parser.add_argument("--channel", required=True)
    prepare_parser.add_argument("--version", required=True)
    prepare_parser.add_argument("--output-dir", type=Path, required=True)
    prepare_parser.add_argument(
        "--scripts-dir",
        type=Path,
        default=Path("scripts"),
        help="Directory holding install-base-deps.sh (defaults to ./scripts).",
    )

    return parser


def _parse_string_array(raw: str, option: str) -> list[str]:
    value = json.loads(raw)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SystemExit(f"{option} must be a JSON array of strings")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "plan":
        plan = build_plan(
            image_name=args.image,
            include_nightly=args.include_nightly,
            force=args.force,
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

    if args.command == "write-digest":
        path = write_digest_metadata(
            output_dir=args.output_dir,
            release_id=args.release_id,
            arch=args.arch,
            digest=args.digest,
        )
        print(path)
        return 0

    if args.command == "prepare":
        result = prepare_build_context(
            archive_url=args.archive_url,
            archive_sha256=args.archive_sha256,
            base_image=args.base_image,
            base_family=args.base_family,
            channel=args.channel,
            version=args.version,
            output_dir=args.output_dir,
            scripts_dir=args.scripts_dir,
        )
        print(result.dockerfile)
        return 0

    if args.command == "merge":
        tags = _parse_string_array(args.tags_json, "--tags-json")
        arches = _parse_string_array(args.arches_json, "--arches-json")
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
