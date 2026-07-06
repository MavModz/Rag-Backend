"""Business service modules (vertical slices).

Each module owns its router / schemas / service / repository / models and a clear
boundary, so any one can be extracted into its own deployable later without a
rewrite. M1 activates: conversation, knowledge, identity, model_gateway. The
remaining services (document, meeting_intelligence, memory, workflow,
orchestrator) are reserved as skeletons.
"""
