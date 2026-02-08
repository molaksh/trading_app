# Governance Notifications - How to Know About Pending Proposals

## ✅ NO AUTOMATIC CHANGES

**The governance system will NEVER automatically apply changes.** All proposals require explicit human approval. This document shows you how to know when proposals are pending.

---

## 🎯 Quick Check (Recommended Daily/Weekly)

### Check for Pending Proposals (Summary)
```bash
python governance/check_pending_proposals.py --summary
```

**Output Example:**
```
⚠️  PENDING GOVERNANCE PROPOSALS: 1
================================================================================

1. Proposal ID: d5dc5531-1432-4f76-a5cd-fdad76c2a436
   Environment: paper
   Type: ADJUST_RULE
   Symbols: BTC, ETH
   Summary: Adjust adjust_rule for paper trading...
   Recommendation: DEFER
   Confidence: 45%
   Status: ⏳ AWAITING APPROVAL
```

### List Pending Proposals (Table Format)
```bash
python governance/approve_proposal.py --list
```

**Output Example:**
```
⏳ PENDING PROPOSALS (1):

ID                                     ENV    TYPE            REC      CONF
--------------------------------------------------------------------------------
d5dc5531-1432-4f76-a5cd-fdad76c2a436   paper  ADJUST_RULE     DEFER    45%
```

---

## 📋 Detailed Review

### Get Full Details of Pending Proposals
```bash
python governance/check_pending_proposals.py --detailed
```

**Shows:**
- Proposal ID
- Environment (paper/live)
- Type of change (ADD_SYMBOLS, REMOVE_SYMBOLS, ADJUST_RULE, ADJUST_THRESHOLD)
- Symbols affected
- AI recommendation
- Confidence level
- Key risks identified
- Where to find artifacts
- How to approve/reject

---

## 🚨 Alert Generation (For Notifications)

### Generate Alert File (for email/Slack/etc)
```bash
python governance/check_pending_proposals.py --export --output governance_alert.txt
```

**File created:** `governance_alert.txt`
```
================================================================================
🚨 GOVERNANCE ALERT - PENDING PROPOSALS
================================================================================
Timestamp: 2026-02-08T08:51:41.519285
Pending: 1 proposal(s)

[1] PROPOSAL d5dc5531-1432-4f76-a5cd-fdad76c2a436
    Environment: paper
    Type: ADJUST_RULE
    Summary: Adjust adjust_rule for paper trading...
    Recommendation: DEFER
    Confidence: 45%
    Status: AWAITING APPROVAL
    Artifacts: logs/governance/crypto/proposals/d5dc5531-1432-4f76-a5cd-fdad76c2a436

================================================================================
ACTION REQUIRED: Review and approve/reject proposals
================================================================================
```

### Export as JSON (for programmatic monitoring)
```bash
python governance/check_pending_proposals.py --json --output governance_pending.json
```

**File created:** `governance_pending.json`
```json
{
  "timestamp": "2026-02-08T08:51:41.519285",
  "count": 1,
  "proposals": [
    {
      "proposal_id": "d5dc5531-1432-4f76-a5cd-fdad76c2a436",
      "environment": "paper",
      "proposal_type": "ADJUST_RULE",
      "symbols": ["BTC", "ETH"],
      "summary": "...",
      "recommendation": "DEFER",
      "confidence": 0.45,
      "key_risks": [...]
    }
  ]
}
```

---

## 📊 Automated Monitoring Options

### Option 1: Daily Cron Check (Email Alert)
```bash
# Add to crontab
0 9 * * * cd /app && python governance/check_pending_proposals.py --export --output /tmp/governance_alert.txt && mail -s "Governance Alert" admin@example.com < /tmp/governance_alert.txt
```

### Option 2: Slack Webhook Integration
```bash
#!/bin/bash
# Save as check_governance.sh

PENDING=$(python governance/check_pending_proposals.py --json --output /tmp/pending.json)
COUNT=$(jq '.count' /tmp/pending.json)

if [ $COUNT -gt 0 ]; then
  curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/HERE \
    -H 'Content-Type: application/json' \
    -d "{\"text\": \"🚨 $COUNT governance proposal(s) pending approval\"}"
fi
```

### Option 3: Check in Your Monitoring Dashboard
```bash
# Periodically run
python governance/check_pending_proposals.py --json > /var/www/html/governance_status.json
```

Then use a dashboard to display: `governance_status.json`

---

## 🔍 Where to Find Artifacts

All proposal artifacts are stored in:
```
logs/governance/crypto/proposals/<proposal_id>/
├── proposal.json      # Original analysis from Proposer
├── critique.json      # Review from Critic
├── audit.json         # Constitutional check from Auditor
└── synthesis.json     # Human-readable decision (KEY FILE)
```

### View Human-Readable Summary
```bash
cat logs/governance/crypto/proposals/d5dc5531-1432-4f76-a5cd-fdad76c2a436/synthesis.json
```

### View Full Proposal Details
```bash
cat logs/governance/crypto/proposals/d5dc5531-1432-4f76-a5cd-fdad76c2a436/proposal.json
```

### View Constitutional Audit
```bash
cat logs/governance/crypto/proposals/d5dc5531-1432-4f76-a5cd-fdad76c2a436/audit.json
```

---

## ✅ Approval Workflow

### Step 1: Check Pending Proposals
```bash
python governance/check_pending_proposals.py --detailed
```

### Step 2: Read Synthesis (Decision Packet)
```bash
cat logs/governance/crypto/proposals/d5dc5531-1432-4f76-a5cd-fdad76c2a436/synthesis.json | jq .
```

### Step 3: Make Decision

**If you want to APPROVE:**
```bash
python governance/approve_proposal.py \
  --approve d5dc5531-1432-4f76-a5cd-fdad76c2a436 \
  --notes "Reviewed and approved - monitoring enabled"
```

**If you want to REJECT:**
```bash
python governance/approve_proposal.py \
  --reject d5dc5531-1432-4f76-a5cd-fdad76c2a436 \
  --reason "Too much confidence uncertainty, defer to next cycle"
```

### Step 4: Manually Apply Changes (If Approved)
```bash
# Edit your config files based on proposal
# For example: config/crypto/universe_settings.yaml
# Then redeploy
```

---

## 📈 Event Log (Complete History)

All governance events are logged in append-only format:
```bash
cat logs/governance/crypto/logs/governance_events.jsonl
```

**Events include:**
- GOVERNANCE_PROPOSAL_CREATED
- GOVERNANCE_PROPOSAL_CRITIQUED
- GOVERNANCE_PROPOSAL_AUDITED
- GOVERNANCE_PROPOSAL_SYNTHESIZED
- GOVERNANCE_PROPOSAL_APPROVED (manual)
- GOVERNANCE_PROPOSAL_REJECTED (manual)
- GOVERNANCE_PROPOSAL_EXPIRED (72h no action)

---

## 🗓️ Proposal Lifecycle

```
Week 1 (Sunday 3:15 AM ET)
  ↓
[Governance job runs]
  ↓
[Creates proposal: d5dc5531...]
  ↓
[Status: ⏳ AWAITING APPROVAL]
  ↓
[You see alert via check_pending_proposals.py]
  ↓
Week 1-3 (72-hour window)
  ↓
[You can APPROVE or REJECT]
  ↓
If APPROVED:
  ↓
  [You manually apply config changes]
  ↓
  [Redeploy]

If REJECTED:
  ↓
  [Proposal archived, no changes]

If NO ACTION:
  ↓
  [After 72 hours: PROPOSAL EXPIRES]
  ↓
  [No changes applied]
```

---

## 🚨 Key Points

✅ **You are always in control:**
- Governance NEVER applies changes automatically
- All proposals require explicit human approval
- You decide whether to implement suggested changes
- Full transparency: see all agent reasoning

✅ **Multiple ways to monitor:**
- Manual check: `check_pending_proposals.py`
- Automated alerts: Cron + email/Slack
- JSON export: For custom dashboards
- Event log: Complete audit trail

✅ **No time pressure:**
- 72-hour approval window
- Can review in detail before deciding
- Rejection is always an option
- Expired proposals cause no changes

---

## ⚡ Quick Reference

```bash
# Check status (quick)
python governance/check_pending_proposals.py --summary

# Check status (detailed)
python governance/check_pending_proposals.py --detailed

# List in table format
python governance/approve_proposal.py --list

# Generate alert file
python governance/check_pending_proposals.py --export

# Approve a proposal
python governance/approve_proposal.py --approve <id> --notes "reason"

# Reject a proposal
python governance/approve_proposal.py --reject <id> --reason "why"

# View pending proposals as JSON
python governance/check_pending_proposals.py --json

# View event log
cat logs/governance/crypto/logs/governance_events.jsonl
```

---

**Bottom Line:** You have full visibility into what's pending. No changes happen without your explicit approval. ✅
