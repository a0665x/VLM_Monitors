# Documentation Index - VLM_Monitors

> Complete documentation reference for developers and AI agents.

---

## 🎯 Quick Navigation

### For New Developers / AI Agents
**Start Here**: 
1. [`PROJECT_MAP.md`](./PROJECT_MAP.md) - Progressive-disclosure onboarding entrypoint
2. [`ARCHITECTURE.md`](./ARCHITECTURE.md) - Current runtime architecture and flow
3. [`../specs/FAQ.md`](../specs/FAQ.md) - Critical MediaMTX/HLS troubleshooting lessons

### For End Users
- [`../README.md`](../README.md) - Quick start guide
- [`USER_MANUAL.md`](./USER_MANUAL.md) - User manual

---

## 📂 Documentation Structure

### Core Documentation
| File | Purpose | Audience |
|------|---------|----------|
| **[PROJECT_MAP.md](./PROJECT_MAP.md)** | Level 1 onboarding map and change guide | Developers, AI Agents |
| **[ARCHITECTURE.md](./ARCHITECTURE.md)** | Current runtime architecture and flow | Developers, AI Agents |
| **[MODULES.md](./MODULES.md)** | Source tree ownership map | Developers, AI Agents |
| **[RUNTIME.md](./RUNTIME.md)** | Commands, ports, logs, and runtime dependencies | Developers, Operators |
| **[API.md](./API.md)** | REST and Socket.IO endpoint map | Developers |
| **[TESTING.md](./TESTING.md)** | Automated and manual verification guide | Developers, AI Agents |
| **[PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md)** | Broad technical reference including architecture, data flow, performance notes | Developers, AI Agents |
| **[TROUBLESHOOTING.md](./TROUBLESHOOTING.md)** | Recent field fixes, failure modes, and debugging reminders | Developers, Operators |
| **[TODO.md](./TODO.md)** | Follow-up engineering and optimization backlog | Developers |
| **[specs/FAQ.md](../specs/FAQ.md)** | Troubleshooting guide with lessons learned and common mistakes to avoid | Developers, AI Agents |
| **[PRD.md](./PRD.md)** | Product requirements document | Product Managers, Developers |
| **[../README.md](../README.md)** | Quick start and usage guide | End Users |

### Development Artifacts
| File | Purpose | Created By |
|------|---------|-----------|
| **`~/.gemini/antigravity/brain/<conversation-id>/walkthrough.md`** | Session work summaries when present | AI Agent |
| **`~/.gemini/antigravity/brain/<conversation-id>/implementation_plan.md`** | Technical implementation plans when present | AI Agent |
| **`~/.gemini/antigravity/brain/<conversation-id>/task.md`** | Task tracking checklist when present | AI Agent |

### Additional Resources
| File | Purpose |
|------|---------|
| **[USER_MANUAL.md](./USER_MANUAL.md)** | End user manual |
| **[references/documentation-inventory.md](./references/documentation-inventory.md)** | Classification of existing docs and stale references |

---

## 🚨 Critical Reading for AI Agents

### Before Making Any Changes, Read:

1. **[../specs/FAQ.md](../specs/FAQ.md) - Section: "Common Mistakes to Avoid"**
   - MediaMTX configuration pitfalls
   - HLS 404 debugging (hlsAlwaysRemux issue)
   - Video pipeline optimization mistakes

2. **[ARCHITECTURE.md](./ARCHITECTURE.md)**
   - Video pipeline data flow
   - MediaMTX configuration requirements
   - Performance benchmarks and limitations

3. **[RUNTIME.md](./RUNTIME.md)**
   - Current Docker runtime, ports, logs, and verification commands

---

## 📋 Key Topics Index

### Video Streaming
- **Architecture**: [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- **Troubleshooting**: [`../specs/FAQ.md`](../specs/FAQ.md)
- **Runtime checks**: [`RUNTIME.md`](./RUNTIME.md)

### MediaMTX Configuration
- **Settings**: [`RUNTIME.md`](./RUNTIME.md)
- **Critical Issues**: [`../specs/FAQ.md`](../specs/FAQ.md)
- **HLS 404 Fix**: [`../specs/FAQ.md`](../specs/FAQ.md)

### Performance Optimization
- **Benchmarks**: [`PROJECT_OVERVIEW.md`](./PROJECT_OVERVIEW.md)
- **HLS Latency**: [`../specs/FAQ.md`](../specs/FAQ.md)
- **System Resources**: [`RUNTIME.md`](./RUNTIME.md)

### Debugging
- **Tools**: [`RUNTIME.md`](./RUNTIME.md)
- **Docker Issues**: [`../specs/FAQ.md`](../specs/FAQ.md)
- **Lessons**: [`../specs/FAQ.md`](../specs/FAQ.md)

---

## 🔄 Documentation Update History

| Date | Changes | Files Updated |
|------|---------|---------------|
| 2026-02-08 | Created comprehensive project overview with architecture diagrams | PROJECT_OVERVIEW.md |
| 2026-02-08 | Rewrote FAQ with HLS optimization lessons and critical mistakes | specs/FAQ.md |
| 2026-02-08 | Added HLS latency optimization walkthrough | walkthrough.md |
| 2026-02-08 | Created documentation index | DOCUMENTATION_INDEX.md |

---

## 📝 Contributing to Documentation

### When to Update Documentation

**Must Update**:
- After fixing a critical bug → Add to [`../specs/FAQ.md`](../specs/FAQ.md)
- After major architectural change → Update [`ARCHITECTURE.md`](./ARCHITECTURE.md) and [`PROJECT_OVERVIEW.md`](./PROJECT_OVERVIEW.md)
- After completing work session → Create/update `walkthrough.md`
- When adding new features → Update [`PRD.md`](./PRD.md), [`../README.md`](../README.md), and relevant `spec/` files

**Optional**:
- Minor bug fixes → Consider adding to FAQ if lesson learned
- Code refactoring → Update if impacts architecture
- Dependency updates → Note in [`RUNTIME.md`](./RUNTIME.md) if significant

### Documentation Standards

1. **Be Specific**: Include exact commands, file paths, line numbers
2. **Include Context**: Explain WHY, not just WHAT
3. **Add Examples**: Show before/after, good/bad patterns
4. **Link Liberally**: Cross-reference related sections
5. **Keep Updated**: Remove outdated information promptly

---

## 🎯 Quick Reference - Most Common Tasks

### Video Stream Not Working
→ [`../specs/FAQ.md`](../specs/FAQ.md)

### HLS Returns 404
→ [`../specs/FAQ.md`](../specs/FAQ.md)

### Reduce Video Latency
→ [`../specs/FAQ.md`](../specs/FAQ.md)

### Docker Container Issues
→ [`../specs/FAQ.md`](../specs/FAQ.md)

### Understanding Architecture
→ [`PROJECT_MAP.md`](./PROJECT_MAP.md)

---

**Last Updated**: 2026-02-08  
**Maintainer**: [Add maintainer info]  
**Version**: 2.0.0
