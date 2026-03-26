// Run these in Neo4j Browser after loading to verify everything worked
// Open Neo4j Browser → paste each query → press Ctrl+Enter

// ── 1. Quick count check ──────────────────────────────────
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY count DESC;

// ── 2. Check SPAWNED chains exist (parent→child trees) ────
MATCH (parent:Process)-[:SPAWNED]->(child:Process)
RETURN parent.cmdLine AS parent, parent.processId AS ppid,
       child.cmdLine  AS child,  child.processId  AS cpid
LIMIT 10;

// ── 3. Find the evil=1 attack events ──────────────────────
MATCH (p:Process)-[:EMITS]->(e:SyscallEvent {evil: 1})
RETURN p.processName AS process, p.processId AS pid,
       e.eventName   AS syscall, e.timestamp  AS time
ORDER BY e.timestamp;

// ── 4. Trace the attack chain (the SSH credential theft) ──
MATCH (grandparent:Process)-[:SPAWNED]->(parent:Process)-[:SPAWNED]->(child:Process)
WHERE child.processId IN [
    // replace with actual evil PIDs from query 3 above
    1323, 1246
]
RETURN grandparent.cmdLine AS gp,
       parent.cmdLine      AS parent,
       child.cmdLine       AS child;

// ── 5. Show sensitive file access (has_sensitive_path=true) ─
MATCH (p:Process)-[:ACCESSED]->(f:File {has_sensitive_path: true})
RETURN p.processName AS process, f.path AS file
LIMIT 20;

// ── 6. Count by split verification ───────────────────────
// Expected: train ~763k, val ~188k, test ~188k total events
MATCH (e:SyscallEvent)
RETURN count(e) AS total_syscall_events;

// ── 7. Test context_retriever.py query manually ──────────
// Replace 1323 with an actual evil processId from query 3
MATCH (p:Process {id: "1323"})
OPTIONAL MATCH (parent:Process)-[:SPAWNED]->(p)
OPTIONAL MATCH (grandparent:Process)-[:SPAWNED]->(parent)
OPTIONAL MATCH (p)-[:ACCESSED]->(f:File)
OPTIONAL MATCH (p)-[:CONNECTED_TO]->(n:Network)
RETURN grandparent.cmdLine AS Grandparent,
       parent.cmdLine      AS Parent,
       p.cmdLine           AS Target,
       collect(DISTINCT f.path) AS Files,
       collect(DISTINCT n.domain) AS Networks;
