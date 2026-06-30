#!/usr/bin/env python3
"""
Audit Overlap Calculator
Uses the Enhanced Framework Schema v3.0 to calculate precise control overlap
"""

import json
from typing import List, Set, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class ScopeType(Enum):
    BASELINE = "baseline"
    OPTIONAL_ADDON = "optional_addon"
    TIER = "tier"
    OVERLAY = "overlay"
    ANNEX = "annex"
    ENHANCEMENT = "enhancement"

@dataclass
class AuditScope:
    """Represents a user's selected audit scope"""
    framework_id: str
    components: List[str]  # component_ids to include
    tier_name: Optional[str] = None  # For tiered frameworks

class OverlapCalculator:
    def __init__(self, frameworks_json_path: str):
        with open(frameworks_json_path, 'r') as f:
            self.data = json.load(f)
        self.frameworks = self.data.get('frameworks', {})
    
    def get_framework(self, framework_id: str) -> Dict[str, Any]:
        """Get a framework by ID"""
        return self.frameworks.get(framework_id, {})
    
    def get_component(self, framework_id: str, component_id: str) -> Dict[str, Any]:
        """Get a specific component from a framework"""
        framework = self.get_framework(framework_id)
        for comp in framework.get('components', []):
            if comp.get('component_id') == component_id:
                return comp
        return {}
    
    def get_nist_controls(self, framework_id: str, component_id: str) -> Set[str]:
        """Get NIST 800-53 control mappings for a component"""
        comp = self.get_component(framework_id, component_id)
        return set(comp.get('nist_800_53_mapping', []))
    
    def get_all_controls_for_scope(self, scope: AuditScope) -> Set[str]:
        """Get all NIST controls for a complete audit scope"""
        all_controls = set()
        
        for comp_id in scope.components:
            controls = self.get_nist_controls(scope.framework_id, comp_id)
            all_controls.update(controls)
        
        return all_controls
    
    def calculate_overlap(self, scope_a: AuditScope, scope_b: AuditScope) -> Dict[str, Any]:
        """Calculate overlap between two audit scopes"""
        controls_a = self.get_all_controls_for_scope(scope_a)
        controls_b = self.get_all_controls_for_scope(scope_b)
        
        intersection = controls_a & controls_b
        unique_to_a = controls_a - controls_b
        unique_to_b = controls_b - controls_a
        union = controls_a | controls_b
        
        return {
            "scope_a": {
                "framework": scope_a.framework_id,
                "components": scope_a.components,
                "total_controls": len(controls_a),
                "unique_controls": len(unique_to_a)
            },
            "scope_b": {
                "framework": scope_b.framework_id,
                "components": scope_b.components,
                "total_controls": len(controls_b),
                "unique_controls": len(unique_to_b)
            },
            "overlap": {
                "shared_controls": len(intersection),
                "shared_control_ids": sorted(list(intersection)),
                "total_unique_controls": len(union)
            },
            "metrics": {
                "overlap_percentage": round(len(intersection) / len(union) * 100, 1) if union else 0,
                "a_covers_b_percentage": round(len(intersection) / len(controls_b) * 100, 1) if controls_b else 0,
                "b_covers_a_percentage": round(len(intersection) / len(controls_a) * 100, 1) if controls_a else 0
            }
        }
    
    def get_baseline_components(self, framework_id: str) -> List[Dict[str, Any]]:
        """Get only baseline (required) components for a framework"""
        framework = self.get_framework(framework_id)
        return [c for c in framework.get('components', []) 
                if c.get('scope_type') == 'baseline']
    
    def get_optional_components(self, framework_id: str) -> List[Dict[str, Any]]:
        """Get optional add-on components for a framework"""
        framework = self.get_framework(framework_id)
        return [c for c in framework.get('components', []) 
                if c.get('scope_type') == 'optional_addon']
    
    def get_tier_components(self, framework_id: str) -> List[Dict[str, Any]]:
        """Get tier-based components for a framework, sorted by ordinal"""
        framework = self.get_framework(framework_id)
        tiers = [c for c in framework.get('components', []) 
                 if c.get('scope_type') == 'tier']
        return sorted(tiers, key=lambda x: x.get('tier', {}).get('tier_ordinal', 0))
    
    def get_incremental_controls(self, framework_id: str, from_tier: str, to_tier: str) -> Set[str]:
        """Calculate controls added when moving from one tier to another"""
        from_controls = self.get_nist_controls(framework_id, from_tier)
        to_controls = self.get_nist_controls(framework_id, to_tier)
        return to_controls - from_controls


def demo():
    """Demonstrate the overlap calculator"""
    
    # Load the framework examples
    calc = OverlapCalculator('framework_examples.json')
    
    print("=" * 60)
    print("AUDIT OVERLAP CALCULATOR DEMO")
    print("=" * 60)
    
    # Example 1: SOC 2 Security only vs SOC 2 with all TSCs
    print("\n--- Example 1: SOC 2 Baseline vs SOC 2 Full ---")
    
    soc2_baseline = AuditScope(
        framework_id="soc2_tsc",
        components=["soc2_security"]
    )
    
    soc2_full = AuditScope(
        framework_id="soc2_tsc",
        components=["soc2_security", "soc2_availability", "soc2_processing_integrity", 
                   "soc2_confidentiality", "soc2_privacy"]
    )
    
    result = calc.calculate_overlap(soc2_baseline, soc2_full)
    print(f"SOC 2 Baseline controls: {result['scope_a']['total_controls']}")
    print(f"SOC 2 Full (all TSCs) controls: {result['scope_b']['total_controls']}")
    print(f"Additional controls for full scope: {result['scope_b']['total_controls'] - result['overlap']['shared_controls']}")
    
    # Example 2: List optional components
    print("\n--- Example 2: Optional SOC 2 Components ---")
    optional = calc.get_optional_components("soc2_tsc")
    for comp in optional:
        print(f"  - {comp['component_name']} ({comp.get('tsc_category', 'N/A')})")
    
    # Example 3: FedRAMP tiers
    print("\n--- Example 3: FedRAMP Tier Comparison ---")
    tiers = calc.get_tier_components("fedramp_r5")
    for tier in tiers:
        tier_info = tier.get('tier', {})
        print(f"  {tier_info.get('tier_name')}: ~{tier.get('control_count', 'N/A')} controls")
    
    print("\n" + "=" * 60)
    print("To use: Create AuditScope objects and call calculate_overlap()")
    print("=" * 60)


if __name__ == "__main__":
    demo()
