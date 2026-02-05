"""
Test crypto model approval gates and promotion workflow.
"""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime

from crypto.artifacts import CryptoArtifactStore


class TestModelApprovalGates:
    """Test model approval gates and promotion."""
    
    @pytest.fixture
    def artifact_store(self):
        """Create temporary artifact store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            crypto_root = f"{tmpdir}/crypto/kraken"
            yield CryptoArtifactStore(root=crypto_root)
    
    def test_save_and_verify_integrity(self, artifact_store):
        """Test saving model and verifying integrity."""
        model_data = {'weights': [0.1, 0.2, 0.3]}
        metadata = {'version': '1.0'}
        metrics = {'sharpe': 0.8}
        
        candidate_path = artifact_store.save_candidate(
            'model_001',
            model_data,
            metadata,
            metrics,
        )
        
        # Verify integrity
        assert artifact_store.verify_candidate_integrity('model_001')
    
    def test_integrity_fails_on_modified_file(self, artifact_store):
        """Test that integrity check fails if file is modified."""
        model_data = {'weights': [0.1, 0.2]}
        metadata = {'version': '1.0'}
        metrics = {'sharpe': 0.7}
        
        candidate_path = artifact_store.save_candidate(
            'model_002',
            model_data,
            metadata,
            metrics,
        )
        
        # Modify metadata
        metadata_file = candidate_path / "metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump({'version': '2.0'}, f)
        
        # Integrity should fail
        assert not artifact_store.verify_candidate_integrity('model_002')
    
    def test_load_approved_model_not_found(self, artifact_store):
        """Test loading approved model when none exists."""
        result = artifact_store.load_approved_model()
        assert result is None
    
    def test_approved_model_workflow(self, artifact_store):
        """Test complete approval workflow."""
        # 1. Save candidate
        model_data = {'weights': [0.5]}
        metadata = {'version': '1.0', 'features': ['rsi']}
        metrics = {'sharpe': 0.75, 'dd': 0.10}
        
        artifact_store.save_candidate('model_first', model_data, metadata, metrics)
        
        # 2. Verify integrity
        assert artifact_store.verify_candidate_integrity('model_first')
        
        # 3. Create validation result (PASS)
        validation = {
            'model_id': 'model_first',
            'passed': True,
            'checks': {
                'integrity': True,
                'oos_sharpe': 0.75,
                'max_drawdown': 0.10,
            },
        }
        
        validation_file = artifact_store.validations_dir / "model_first.json"
        with open(validation_file, 'w') as f:
            json.dump(validation, f)
        
        # 4. Create approved pointer
        approved_pointer = {
            'model_id': 'model_first',
            'status': 'approved',
            'promoted_at': datetime.now().isoformat(),
        }
        
        approved_file = artifact_store.models_dir / "approved_model.json"
        with open(approved_file, 'w') as f:
            json.dump(approved_pointer, f)
        
        # 5. Load approved model
        loaded = artifact_store.load_approved_model()
        assert loaded is not None
        assert loaded['model_id'] == 'model_first'
        assert loaded['status'] == 'approved'
    
    def test_approved_model_rollback(self, artifact_store):
        """Test rollback to previous approved model."""
        # Save two candidates
        artifact_store.save_candidate(
            'model_v1',
            {'weights': [0.1]},
            {'version': '1.0'},
            {'sharpe': 0.5},
        )
        
        artifact_store.save_candidate(
            'model_v2',
            {'weights': [0.2]},
            {'version': '2.0'},
            {'sharpe': 0.8},  # Better model
        )
        
        models_dir = artifact_store.models_dir
        
        # Promote v1 to approved
        v1_pointer = {'model_id': 'model_v1', 'status': 'approved'}
        with open(models_dir / "approved_model.json", 'w') as f:
            json.dump(v1_pointer, f)
        
        # Promote v2 (backs up v1 to prev)
        with open(models_dir / "approved_model.prev.json", 'w') as f:
            json.dump(v1_pointer, f)
        
        v2_pointer = {'model_id': 'model_v2', 'status': 'approved'}
        with open(models_dir / "approved_model.json", 'w') as f:
            json.dump(v2_pointer, f)
        
        # Verify v2 is approved
        approved = artifact_store.load_approved_model()
        assert approved['model_id'] == 'model_v2'
        
        # Rollback to v1
        with open(models_dir / "approved_model.prev.json", 'r') as f:
            prev = json.load(f)
        with open(models_dir / "approved_model.json", 'w') as f:
            json.dump(prev, f)
        
        # Verify v1 is approved again
        approved = artifact_store.load_approved_model()
        assert approved['model_id'] == 'model_v1'
    
    def test_approval_audit_log(self, artifact_store):
        """Test approval audit log (append-only)."""
        models_dir = artifact_store.models_dir
        approval_log = models_dir / "approvals.jsonl"
        
        # Append first approval
        record1 = {
            'timestamp': datetime.now().isoformat(),
            'model_id': 'model_first',
            'action': 'promote',
            'reason': 'Initial approval',
        }
        
        with open(approval_log, 'a') as f:
            f.write(json.dumps(record1) + '\n')
        
        # Append second approval
        record2 = {
            'timestamp': datetime.now().isoformat(),
            'model_id': 'model_second',
            'action': 'promote',
            'reason': 'Updated model',
        }
        
        with open(approval_log, 'a') as f:
            f.write(json.dumps(record2) + '\n')
        
        # Append rollback
        record3 = {
            'timestamp': datetime.now().isoformat(),
            'action': 'rollback',
            'to_model': 'model_first',
            'reason': 'Emergency rollback',
        }
        
        with open(approval_log, 'a') as f:
            f.write(json.dumps(record3) + '\n')
        
        # Verify all records
        with open(approval_log, 'r') as f:
            lines = f.readlines()
        
        assert len(lines) == 3
        
        audit = [json.loads(line) for line in lines]
        assert audit[0]['action'] == 'promote'
        assert audit[1]['action'] == 'promote'
        assert audit[2]['action'] == 'rollback'
