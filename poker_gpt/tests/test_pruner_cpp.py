"""
test_pruner_cpp.py — Unit tests for C++ pruning module (T4.2c).

Tests the pybind11 bindings for fast solver operations and verifies
fallback behavior when C++ module is unavailable.

Created: 2026-03-03
Task: T4.2c
"""

import json
import pytest
from pathlib import Path
import tempfile

import poker_gpt.solver_pruner_cpp as pruner_cpp


class TestCPPModuleAvailability:
    """Test that the C++ module loads correctly."""

    def test_cpp_module_available(self):
        """Check if C++ module is available (should be true after build)."""
        assert pruner_cpp.is_cpp_available(), "C++ module should be available after build"


class TestExtractActionFrequencies:
    """Test C++ action frequency extraction."""

    @pytest.fixture
    def sample_solver_output(self):
        """Create a minimal solver output JSON for testing."""
        data = {
            "actions": ["CHECK", "BET 33", "BET 75"],
            "strategy": {
                "strategy": {
                    "AsAh": [0.0, 0.8, 0.2],
                    "KsKh": [0.1, 0.6, 0.3],
                    "QsQh": [0.3, 0.5, 0.2],
                }
            }
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_extract_frequencies_cpp(self, sample_solver_output):
        """Test that C++ extraction matches expected values."""
        result = pruner_cpp.extract_action_frequencies_cpp(sample_solver_output)
        
        assert result is not None, "Should return frequencies dict"
        assert "CHECK" in result
        assert "BET 33" in result
        assert "BET 75" in result
        
        # Average of [0.0, 0.1, 0.3] = 0.1333...
        assert abs(result["CHECK"] - 0.1333) < 0.01
        # Average of [0.8, 0.6, 0.5] = 0.6333...
        assert abs(result["BET 33"] - 0.6333) < 0.01
        # Average of [0.2, 0.3, 0.2] = 0.2333...
        assert abs(result["BET 75"] - 0.2333) < 0.01

        sample_solver_output.unlink()  # Clean up

    def test_extract_missing_file(self):
        """Test that extraction handles missing files gracefully."""
        result = pruner_cpp.extract_action_frequencies_cpp(Path("/nonexistent/file.json"))
        assert result is None, "Should return None for missing file"


class TestNormalizeActionNames:
    """Test C++ action name normalization."""

    def test_normalize_chip_amounts(self):
        """Test normalization from chip amounts to percentages."""
        raw = {
            "CHECK": 0.2,
            "BET 2.000000": 0.5,  # 2 BB into 6 BB pot = 33%
            "BET 4.500000": 0.3,  # 4.5 BB into 6 BB pot = 75%
        }
        
        result = pruner_cpp.normalize_action_names_cpp(
            raw,
            pot_size_bb=6.0,
            effective_stack_bb=100.0,
            bet_sizes_pct=[33, 75]
        )
        
        assert result is not None
        assert "CHECK" in result
        assert "BET 33" in result
        assert "BET 75" in result
        assert result["CHECK"] == 0.2
        assert result["BET 33"] == 0.5
        assert result["BET 75"] == 0.3

    def test_normalize_already_normalized(self):
        """Test that already-normalized names pass through correctly."""
        raw = {
            "CHECK": 0.3,
            "BET 33": 0.4,
            "BET 75": 0.3,
        }
        
        result = pruner_cpp.normalize_action_names_cpp(
            raw,
            pot_size_bb=6.0,
            effective_stack_bb=100.0,
            bet_sizes_pct=[33, 75]
        )
        
        assert result == raw


class TestCheckConvergence:
    """Test C++ convergence checking."""

    def test_convergence_uniform_distribution(self):
        """Test that uniform distributions have low standard deviation."""
        freqs = {
            "CHECK": 0.33,
            "BET 33": 0.33,
            "BET 75": 0.34,
        }
        
        result = pruner_cpp.check_convergence_cpp(freqs, threshold=0.01)
        assert result is True, "Uniform distribution should converge"

    def test_convergence_high_variance(self):
        """Test that high-variance distributions don't converge."""
        freqs = {
            "CHECK": 0.9,
            "BET 33": 0.05,
            "BET 75": 0.05,
        }
        
        result = pruner_cpp.check_convergence_cpp(freqs, threshold=0.01)
        assert result is False, "High variance should not converge with tight threshold"

    def test_convergence_custom_threshold(self):
        """Test convergence with different thresholds."""
        freqs = {
            "CHECK": 0.6,
            "BET 33": 0.25,
            "BET 75": 0.15,
        }
        
        # Tight threshold: should not converge
        result_tight = pruner_cpp.check_convergence_cpp(freqs, threshold=0.01)
        assert result_tight is False
        
        # Loose threshold: should converge
        result_loose = pruner_cpp.check_convergence_cpp(freqs, threshold=0.5)
        assert result_loose is True


class TestExtractAndNormalize:
    """Test the combined extract + normalize convenience function."""

    @pytest.fixture
    def chip_amount_output(self):
        """Create solver output with chip amounts (needs normalization)."""
        data = {
            "actions": ["CHECK", "BET 2.000000", "BET 4.500000"],
            "strategy": {
                "strategy": {
                    "AsAh": [0.0, 0.8, 0.2],
                    "KsKh": [0.1, 0.6, 0.3],
                }
            }
        }
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            return Path(f.name)

    def test_extract_and_normalize_cpp(self, chip_amount_output):
        """Test one-call extract + normalize."""
        result = pruner_cpp.extract_and_normalize_cpp(
            chip_amount_output,
            pot_size_bb=6.0,
            effective_stack_bb=100.0,
            bet_sizes_pct=[33, 75]
        )
        
        assert result is not None
        assert "CHECK" in result
        assert "BET 33" in result
        assert "BET 75" in result
        
        # Averages: CHECK = 0.05, BET 33 = 0.7, BET 75 = 0.25
        assert abs(result["CHECK"] - 0.05) < 0.01
        assert abs(result["BET 33"] - 0.7) < 0.01
        assert abs(result["BET 75"] - 0.25) < 0.01

        chip_amount_output.unlink()  # Clean up


class TestFallbackBehavior:
    """Test that functions handle C++ unavailability gracefully."""

    def test_graceful_degradation(self):
        """Test that failures return None instead of crashing."""
        # Even if C++ is available, invalid inputs should return None
        result = pruner_cpp.extract_action_frequencies_cpp(Path("/invalid/path.json"))
        assert result is None, "Should return None on failure, not crash"
