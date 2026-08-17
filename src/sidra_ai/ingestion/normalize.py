"""Turn GitHub API payloads into provenance-carrying :class:`Document`s.

Trust assignment happens here, and it is not uniform:

* README/docs/commits are authored inside SIDRA STUDIO repositories, so they
  are ``INTERNAL_REPO`` - still DATA, but attributable.
* Issue and PR bodies can be written by anyone with an account, so they are
  ``EXTERNAL`` regardless of which repository they sit in. This is the common
  path for a prompt-injection payload reaching a code assistant.

Source timestamps are provenance, not decoration. For GitHub objects that
carry an authoritative authored/updated timestamp (commits, PRs, issues), an
absent or malformed timestamp makes the object non-indexable instead of being
silently replaced with "now". Fabricating a current timestamp can make stale
or malformed source data appear fresh and undermines downstream grounding.
README/docs use the observation time because their exact revision is already
anchored by ``commit_sha``.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
from typing import Any, Mapping

from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel

#: GitHub accounts whose content is still third-party authored.
_BOT_TYPES = frozenset({"Bot"})


def _parse_time(value: str | None) -> datetime | None:
    """Parse an authoritative GitHub timestamp as UTC.

    ``None`` means the source did not provide a trustworthy timestamp. Callers
    that normalize authored GitHub objects must then fail closed rather than
    inventing the current time.
    """

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _mutable_timestamp(payload: Mapping[str, Any]) -> datetime | None:
    """Return a trustworthy timestamp for a mutable GitHub object.

    A genuinely absent ``updated_at`` key may use GitHub's authoritative
    creation timestamp as a conservative compatibility fallback. A present but
    empty, null, malformed, or naive ``updated_at`` is different: the payload
    claims to carry a revision timestamp but it cannot be trusted, so silently
    substituting an older creation time would hide source corruption. Those
    cases fail closed.
    """

    if "updated_at" in payload:
        return _parse_time(payload.get("updated_at"))
    return _parse_time(payload.get("created_at"))


def decode_content(payload: Mapping[str, Any]) -> str:
    """Decode a GitHub contents payload. Binary files return ``""``."""

    encoding = payload.get("encoding")
    raw = payload.get("content") or ""
    if encoding != "base64":
        return str(raw)
    try:
        return base64.b64decode(raw).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return ""


def _author(payload: Mapping[str, Any]) -> str:
    user = payload.get("user") or payload.get("author") or {}
    if isinstance(user, dict):
        login = user.get("login") or ""
        if user.get("type") in _BOT_TYPES and login:
            return f"{login} (bot)"
        return str(login)
    return ""


def readme_document(
    payload: Mapping[str, Any], *, repository: str, commit_sha: str, license: str
) -> Document | None:
    content = decode_content(payload)
    if not content.strip():
        return None
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=repository,
            path=str(payload.get("path") or "README.md"),
            commit_sha=commit_sha,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.README,
            trust_level=TrustLevel.INTERNAL_REPO,
            license=license,
            url=str(payload.get("html_url") or ""),
        ),
    )


def doc_document(
    payload: Mapping[str, Any], *, repository: str, commit_sha: str, license: str
) -> Document | None:
    content = decode_content(payload)
    if not content.strip():
        return None
    return Document(
        content=content,
        provenance=Provenance(
            source="github",
            repository=repository,
            path=str(payload.get("path") or "docs/unknown"),
            commit_sha=commit_sha,
            timestamp=datetime.now(timezone.utc),
            source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO,
            license=license,
            url=str(payload.get("html_url") or ""),
        ),
    )


def commit_document(
    payload: Mapping[str, Any], *, repository: str, license: str
) -> Document | None:
    sha = str(payload.get("sha") or "")
    commit = payload.get("commit") or {}
    message = str(commit.get("message") or "").strip()
    if not sha or not message:
        return None

    author_meta = commit.get("author") or {}
    committer_meta = commit.get("committer") or {}
    timestamp = _parse_time(author_meta.get("date")) or _parse_time(
        committer_meta.get("date")
    )
    if timestamp is None:
        return None

    files = payload.get("files") or []
    changed = ", ".join(str(f.get("filename", "")) for f in files[:20])
    body = message if not changed else f"{message}\n\nchanged files: {changed}"

    return Document(
        content=body,
        provenance=Provenance(
            source="github",
            repository=repository,
            path=f"commit/{sha[:12]}",
            commit_sha=sha,
            timestamp=timestamp,
            source_type=SourceType.COMMIT,
            trust_level=TrustLevel.INTERNAL_REPO,
            license=license,
            url=str(payload.get("html_url") or ""),
            author=_author(payload) or str(author_meta.get("name") or ""),
        ),
    )


def pull_request_document(
    payload: Mapping[str, Any], *, repository: str, commit_sha: str, license: str
) -> Document | None:
    number = payload.get("number")
    title = str(payload.get("title") or "").strip()
    if number is None or not title:
        return None
    body = str(payload.get("body") or "").strip()
    head_sha = str(((payload.get("head") or {}).get("sha")) or "")
    timestamp = _mutable_timestamp(payload)
    if timestamp is None:
        return None

    return Document(
        content=f"# PR #{number}: {title}\n\n{body}".strip(),
        provenance=Provenance(
            source="github",
            repository=repository,
            path=f"pull/{number}",
            # Anchor the citation to the allowlisted base repository revision
            # at which this mutable PR was observed. A PR head SHA may belong
            # to an untrusted fork and must not masquerade as a commit in the
            # allowlisted base repository. Preserve it separately as DATA.
            commit_sha=commit_sha,
            timestamp=timestamp,
            source_type=SourceType.PULL_REQUEST,
            # Third-party authored: treat as external input.
            trust_level=TrustLevel.EXTERNAL,
            license=license,
            url=str(payload.get("html_url") or ""),
            author=_author(payload),
            extra={
                "state": payload.get("state"),
                "merged": payload.get("merged_at") is not None,
                "head_sha": head_sha,
            },
        ),
    )


def issue_document(
    payload: Mapping[str, Any], *, repository: str, commit_sha: str, license: str
) -> Document | None:
    number = payload.get("number")
    title = str(payload.get("title") or "").strip()
    if number is None or not title:
        return None
    body = str(payload.get("body") or "").strip()
    timestamp = _mutable_timestamp(payload)
    if timestamp is None:
        return None

    return Document(
        content=f"# Issue #{number}: {title}\n\n{body}".strip(),
        provenance=Provenance(
            source="github",
            repository=repository,
            path=f"issue/{number}",
            commit_sha=commit_sha,
            timestamp=timestamp,
            source_type=SourceType.ISSUE,
            trust_level=TrustLevel.EXTERNAL,
            license=license,
            url=str(payload.get("html_url") or ""),
            author=_author(payload),
            extra={"state": payload.get("state")},
        ),
    )
