## Before submitting

- [x] I searched [existing issues](https://github.com/thedotmack/claude-mem/issues) and confirmed this is not a duplicate

---

## Bug Description

`search` MCP tool fails on Windows with `onnxruntime-common` package resolution error. `save_memory` and `get_observations` work fine (SQLite path). Two related issues:

1. **Chroma auto-start fails**: `npx.cmd chroma run` exits with code 1 immediately on startup
2. **Embedding init fails**: Even when Chroma is manually running on port 8000, the collection setup crashes because Bun can't resolve `onnxruntime-common` from its global cache

### Steps to Reproduce

1. Install claude-mem on Windows via `/plugin marketplace add thedotmack/claude-mem`
2. Install chromadb via `pip install chromadb` (tried both 0.6.3 and 1.5.0)
3. Restart Claude Code
4. Use `save_memory` tool — works fine
5. Use `search` tool — fails with error below

### Expected Behavior

`search` should return semantically matched results from the vector database.

### Error Message

```
Worker API error (500): {
  "error": "Collection setup failed: ResolveMessage: ENOENT while resolving package 'onnxruntime-common' from 'C:\\Users\\Surfinite\\.bun\\install\\cache\\@huggingface\\transformers@3.8.1@@@1\\dist\\transformers.node.mjs'"
}
```

### Environment

- **Claude-mem version**: 10.0.7
- **Claude Code version**: 2.1.42 (VSCode extension)
- **OS**: Windows 11 Pro 10.0.26100 (x64)
- **Bun**: 1.3.9
- **Node**: v24.13.0
- **Python**: 3.13.12
- **chromadb (pip)**: 0.6.3

### Logs

From `~/.claude-mem/logs/claude-mem-2026-02-15.log`:

**Chroma auto-start failure:**
```
[00:33:52.078] [CHROMA_SERVER] Starting Chroma server {command=npx.cmd, args=chroma run --path C:\Users\Surfinite\.claude-mem\vector-db --host 127.0.0.1 --port 8000}
[00:33:53.337] [CHROMA_SERVER] Server process exited {code=1, signal=null}
[00:34:52.532] [CHROMA_SERVER] Server failed to start within timeout {timeoutMs=60000}
[00:34:52.532] Chroma server failed to start - vector search disabled
```

**onnxruntime resolution failure (after manually starting Chroma on port 8000):**
```
[01:00:24.487] [CHROMA] SDK chroma sync failed, continuing without vector search {obsId=16} Collection setup failed: ResolveMessage: ENOENT while resolving package 'onnxruntime-common' from 'C:\Users\Surfinite\.bun\install\cache\@huggingface\transformers@3.8.1@@@1\dist\transformers.node.mjs'
```

### What I Tried

1. `pip install chromadb` (both 1.5.0 and 0.6.3) — Chroma heartbeat works, onnxruntime error persists
2. `bun install` in `~/.claude/plugins/cache/thedotmack/claude-mem/10.0.7/` — installs `@chroma-core/default-embed`
3. `bun add onnxruntime-common onnxruntime-node` in plugin dir — installs to node_modules but error remains (Bun resolves from global cache)
4. `bun pm trust --all` — postinstall scripts ran OK
5. `bun install --force` — no change
6. Multiple Claude Code restarts

### Additional Context

The root cause appears to be Bun's global cache module resolution on Windows. `@huggingface/transformers@3.8.1` depends on `onnxruntime-node@1.21.0` which depends on `onnxruntime-common`. The package exists in the Bun global cache (`~/.bun/install/cache/onnxruntime-common/1.21.0@@@1/`) but Bun can't resolve it when loading `transformers.node.mjs` from the cache path.

**Possible fix**: Pin `onnxruntime-common` as a direct dependency in claude-mem's `package.json` so it's in the local `node_modules/` resolution scope rather than relying on Bun's transitive resolution from the global cache.
