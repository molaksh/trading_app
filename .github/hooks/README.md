# Git Hooks

This directory contains git hooks for repository hygiene.

## Enforce Documentation Policy

**File**: `enforce-doc-policy.py`

This hook enforces the single-source-of-truth documentation policy:

1. **No new `.md` files** allowed (except `DOCUMENTATION.md` and `README.md`)
2. **New documentation** must be prepended to the top of `DOCUMENTATION.md` (under "## 🔔 Latest Updates")
3. **No appending** to the bottom of documentation files
4. **Proper structure** required (Latest Updates + Historical Record sections)

### Install as Pre-Commit Hook

```bash
# Create symbolic link
ln -s ../../.github/hooks/enforce-doc-policy.py .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Test it
git commit --allow-empty -m "test"
```

### Run Manually

```bash
# Check current staged changes
python3 .github/hooks/enforce-doc-policy.py

# Check all changed files (not just staged)
# (modify script to pass staged_only=False)
```

### Bypass Hook (if necessary)

```bash
git commit --no-verify -m "message"
```

---

## Policy Details

### DOCUMENTATION.md Structure

```markdown
# Repository Documentation (Single Source of Truth)

## 🔔 Latest Updates (Newest First)

### YYYY-MM-DD — Title

**Scope**: Component / Phase
**Audience**: Audience type

Content...

---

(Older entries appear below)

## 📚 Historical Record (Oldest at Bottom)

...previous entries...
```

### Rules

1. **New entries go at the TOP** under "## 🔔 Latest Updates"
2. **Use date-first format**: `YYYY-MM-DD — Short Title`
3. **Always include Scope and Audience metadata**
4. **Never modify old entries silently** — create a new entry describing the update
5. **No new `.md` files** for documentation

### Enforcement

This hook runs automatically on `git commit`. Violations block the commit.

To override (only when necessary):
```bash
git commit --no-verify
```

---

*Last updated: 2026-02-05*
