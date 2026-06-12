"""
#2E — Source provider abstraction
=================================
Decouples the C-parsing / diff / context logic from *where* source bytes come
from. Two providers share one interface:

  * ``FilesystemSourceProvider`` — walks a local folder (back-compat + the
    import-from-disk step that fills the DB).
  * ``DbReleaseSourceProvider`` — reads gzip-compressed blobs stored in the DB
    keyed by release, decompressing one file at a time (lazy, never loads a whole
    tree into RAM).

Both expose:
  * ``list_files(exts=None) -> list[SourceFile]`` — cheap listing, no content read.
  * ``read_file(rel_path) -> str | None`` — read ONE file's text.
  * ``iter_text(exts=None) -> (rel_path, text)`` — generator used by the importer.
  * ``change_key(sf) -> tuple`` — change-detection key for diff stat-gating
    (DB: content hash; filesystem: size+mtime).

The scanning constants below are the canonical home; ``Logic_Code_Index`` mirrors
them. Keep them in sync if the supported source extensions change.
"""
from dataclasses import dataclass, field
import hashlib
import os
from typing import List, Optional, Iterator, Tuple

# Canonical source-scanning rules (mirror Logic_Code_Index).
SOURCE_EXTENSIONS = {".c", ".h", ".cpp", ".hpp", ".cc", ".hh", ".cxx"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2 MB — skip anything larger
SKIP_DIRS = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules",
    "bin", "obj", "build", "output", "out", "debug", "release",
    "polyspace", "misra", "lint", "doc", "docs", "documentation",
    "compiler_warnings", "toolcfg", "tools", "scripts",
    "ci-scripts", "architecture", "gitlab_config",
}


@dataclass
class SourceFile:
    rel_path: str
    size: int
    ext: str
    content_hash: str = ""   # sha256 of content (DB provider has it; FS lazy)
    mtime: float = 0.0       # filesystem mtime (FS provider only)


def _norm_rel(rel_path: str) -> str:
    """Normalise to forward-slash relative paths so DB keys are OS-independent."""
    return rel_path.replace(os.sep, "/")


class FilesystemSourceProvider:
    """Reads source from a local directory (or a single file)."""

    def __init__(self, root: str):
        self.root = root

    def list_files(self, exts=None) -> List[SourceFile]:
        exts = exts or SOURCE_EXTENSIONS
        out: List[SourceFile] = []
        if not self.root:
            return out
        if os.path.isfile(self.root):
            ext = os.path.splitext(self.root)[1].lower()
            if ext in exts:
                try:
                    st = os.stat(self.root)
                    if 0 < st.st_size <= MAX_FILE_SIZE:
                        out.append(SourceFile(os.path.basename(self.root),
                                              st.st_size, ext, mtime=st.st_mtime))
                except OSError:
                    pass
            return out
        for dirpath, dirs, names in os.walk(self.root):
            if os.path.basename(dirpath).lower() in SKIP_DIRS:
                dirs.clear()
                continue
            for name in names:
                ext = os.path.splitext(name)[1].lower()
                if ext not in exts:
                    continue
                ap = os.path.join(dirpath, name)
                try:
                    st = os.stat(ap)
                except OSError:
                    continue
                if not (0 < st.st_size <= MAX_FILE_SIZE):
                    continue
                rel = _norm_rel(os.path.relpath(ap, self.root))
                out.append(SourceFile(rel, st.st_size, ext, mtime=st.st_mtime))
        out.sort(key=lambda s: s.rel_path)
        return out

    def _abspath(self, rel_path: str) -> str:
        if os.path.isfile(self.root):
            return self.root
        return os.path.join(self.root, rel_path.replace("/", os.sep))

    def read_file(self, rel_path: str) -> Optional[str]:
        try:
            with open(self._abspath(rel_path), "r", encoding="utf-8",
                      errors="replace") as f:
                return f.read()
        except OSError:
            return None

    def iter_text(self, exts=None) -> Iterator[Tuple[str, str]]:
        for sf in self.list_files(exts):
            text = self.read_file(sf.rel_path)
            if text is not None:
                yield sf.rel_path, text

    def change_key(self, sf: SourceFile) -> tuple:
        return (sf.size, sf.mtime)


class DbReleaseSourceProvider:
    """Reads source stored in the DB for one release (lazy per-file decompress)."""

    def __init__(self, db, release_id: int):
        self.db = db
        self.release_id = release_id

    def list_files(self, exts=None) -> List[SourceFile]:
        rows = self.db.list_release_source_files(self.release_id)
        out = []
        for r in rows:
            if exts and r["ext"] not in exts:
                continue
            out.append(SourceFile(r["rel_path"], r["size"], r["ext"] or "",
                                  content_hash=r["content_hash"] or ""))
        return out

    def read_file(self, rel_path: str) -> Optional[str]:
        return self.db.read_release_source_file(self.release_id, rel_path)

    def iter_text(self, exts=None) -> Iterator[Tuple[str, str]]:
        for sf in self.list_files(exts):
            text = self.read_file(sf.rel_path)
            if text is not None:
                yield sf.rel_path, text

    def change_key(self, sf: SourceFile) -> tuple:
        return (sf.content_hash,)


def as_provider(source) -> object:
    """Coerce a path string into a FilesystemSourceProvider; pass providers through.

    Lets refactored consumers accept either a legacy path or a provider so the
    existing path-based call sites and tests keep working unchanged.
    """
    if source is None:
        return FilesystemSourceProvider("")
    if isinstance(source, str):
        return FilesystemSourceProvider(source)
    return source


def release_source_provider(db, release_id):
    """#2E: return a DbReleaseSourceProvider for a release that HAS stored source,
    else None (release_id is None, or the release has no source imported yet)."""
    if db is None or release_id is None:
        return None
    try:
        if not db.has_release_source(release_id):
            return None
    except Exception:
        return None
    return DbReleaseSourceProvider(db, release_id)
