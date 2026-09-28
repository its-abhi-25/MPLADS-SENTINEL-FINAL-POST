"""
Explanation Generator (v3.0)
Produces human-readable explanations for risk assessments.
"""
from typing import Dict, Any, List


class ExplanationGenerator:
    """Generates clear, neutral explanations for risk findings."""
    
    def generate_risk_summary(self, risk_result: Dict[str, Any]) -> str:
        """Generate a one-paragraph risk summary."""
        risk_score = risk_result.get('risk_score', 0)
        risk_level = risk_result.get('risk_level', 'LOW')
        confidence = risk_result.get('confidence', 0)
        active_count = risk_result.get('active_signal_count', 0)
        
        if risk_level == 'CRITICAL':
            opener = f"This project scores {risk_score:.0f}/100 (Critical), indicating significantly anomalous patterns"
        elif risk_level == 'HIGH':
            opener = f"This project scores {risk_score:.0f}/100 (High), indicating notable anomalous patterns"
        elif risk_level == 'MODERATE':
            opener = f"This project scores {risk_score:.0f}/100 (Moderate), indicating some unusual patterns"
        else:
            opener = f"This project scores {risk_score:.0f}/100 (Low), indicating minimal anomalous patterns"
        
        context = f"based on {active_count} independent analytical signals"
        
        confidence_text = f"Confidence in this assessment is {confidence:.0f}%"
        
        return f"{opener} {context}. {confidence_text}."
    
    def generate_investigation_recommendation(self, evidence_items: List[Dict[str, Any]]) -> str:
        """Generate recommended investigation actions based on evidence."""
        recommendations = []
        
        signal_types = [e.get('signal_type') for e in evidence_items]
        
        if 'COST_ANOMALY' in signal_types:
            recommendations.append("Review cost estimates against comparable projects in the same area and category")
        
        if 'DESCRIPTION_SIMILARITY' in signal_types:
            recommendations.append("Examine potentially duplicate or templated work descriptions for consistency")
        
        if 'MP_CONCENTRATION' in signal_types:
            recommendations.append("Review the MP's concentration of works in this category for unusual patterns")
        
        if 'CONSTITUENCY_PATTERN' in signal_types:
            recommendations.append("Analyze constituency-level patterns in work categories and amount distributions")
        
        if 'TEMPORAL_ANOMALY' in signal_types:
            recommendations.append("Investigate temporal clustering for potential batch-processing concerns")
        
        if 'STAGE_CONSISTENCY' in signal_types:
            recommendations.append("Verify work stage status and cross-reference with implementation records")
        
        if 'CROSS_SIGNAL_PATTERN' in signal_types:
            recommendations.append("Multiple independent indicators suggest this project warrants priority review")
        
        if not recommendations:
            recommendations.append("Standard review recommended")
        
        return "; ".join(recommendations)
    
    def generate_signal_explanation(self, evidence_item: Dict[str, Any]) -> str:
        """Generate explanation for a single signal."""
        signal_type = evidence_item.get('signal_type', '')
        explanation = evidence_item.get('explanation', '')
        score = evidence_item.get('signal_score', 0)
        
        if not explanation:
            return f"{signal_type}: score {score:.2f}"
        
        return explanation
