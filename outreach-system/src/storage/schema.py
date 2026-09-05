"""Single source of truth for Airtable table/field names.

Nothing else in the codebase should hardcode a table or field name string -
import from here so a rename in Airtable only needs one edit.
"""

BASE_NAME = "Outreach System"

# --- Businesses ---
TBL_BUSINESSES = "Businesses"

class BusinessFields:
    NAME = "Name"
    CATEGORY = "Category"
    CITY = "City"
    ADDRESS = "Address"
    PHONE = "Phone"
    WEBSITE = "Website"
    LISTING_URL = "Listing URL"
    EMAIL = "Email (enriched)"
    DEDUP_HASH = "Dedup Hash"
    STATUS = "Status"
    LAST_CONTACTED = "Last Contacted"
    FOLLOW_UP_COUNT = "Follow-up Count"
    ASSIGNED_TEMPLATE = "Assigned Template"
    NOTES = "Notes"


class BusinessStatus:
    NEW = "New"
    ENRICHED = "Enriched"
    QUEUED = "Queued"
    CONTACTED = "Contacted"
    FOLLOW_UP_1 = "Follow-up 1"
    FOLLOW_UP_2 = "Follow-up 2"
    FOLLOW_UP_3 = "Follow-up 3"
    RESPONDED = "Responded"
    INTERESTED = "Interested"
    NOT_INTERESTED = "Not Interested"
    OPT_OUT = "Opt-out"
    WRONG_NUMBER = "Wrong Number"
    NEEDS_HUMAN = "Needs Human"

    ALL = [
        NEW, ENRICHED, QUEUED, CONTACTED, FOLLOW_UP_1, FOLLOW_UP_2, FOLLOW_UP_3,
        RESPONDED, INTERESTED, NOT_INTERESTED, OPT_OUT, WRONG_NUMBER, NEEDS_HUMAN,
    ]

    # Statuses that stop the follow-up scheduler (mirrors config/follow_up_policy.yaml)
    STOP_STATUSES = [RESPONDED, INTERESTED, NOT_INTERESTED, OPT_OUT, WRONG_NUMBER, NEEDS_HUMAN]

    FOLLOW_UP_SEQUENCE = [CONTACTED, FOLLOW_UP_1, FOLLOW_UP_2, FOLLOW_UP_3]


# --- Interactions ---
TBL_INTERACTIONS = "Interactions"

class InteractionFields:
    BUSINESS = "Business"           # link to Businesses
    CHANNEL = "Channel"
    DIRECTION = "Direction"
    MESSAGE_BODY = "Message Body"
    TEMPLATE_USED = "Template Used"
    MEDIA_ATTACHED = "Media Attached"
    TIMESTAMP = "Timestamp"
    AI_CLASSIFICATION = "AI Classification"


class Channel:
    WHATSAPP = "WhatsApp"
    EMAIL = "Email"


class Direction:
    OUTBOUND = "Outbound"
    INBOUND = "Inbound"


class AIClassificationLabel:
    INTERESTED = "Interested"
    MORE_INFORMATION = "More Information"
    PRICING = "Pricing"
    CALL_REQUESTED = "Call Requested"
    FOLLOW_LATER = "Follow Later"
    NOT_INTERESTED = "Not Interested"
    WRONG_NUMBER = "Wrong Number"
    OPT_OUT = "Opt-out"
    HUMAN_REVIEW = "Human Review"

    ALL = [
        INTERESTED, MORE_INFORMATION, PRICING, CALL_REQUESTED, FOLLOW_LATER,
        NOT_INTERESTED, WRONG_NUMBER, OPT_OUT, HUMAN_REVIEW,
    ]

    # Labels that route straight to a human (spec Phase 11)
    HANDOFF_LABELS = [INTERESTED, PRICING, CALL_REQUESTED, HUMAN_REVIEW]

    # Labels that stop follow-ups immediately (spec Phase 10)
    STOP_LABELS = [NOT_INTERESTED, OPT_OUT, WRONG_NUMBER]


# --- Templates (optional Airtable mirror of config/templates.yaml) ---
TBL_TEMPLATES = "Templates"


# --- HumanHandoffQueue ---
TBL_HANDOFF_QUEUE = "HumanHandoffQueue"

class HandoffFields:
    BUSINESS = "Business"
    REASON = "Reason"
    PRIORITY = "Priority"
    ASSIGNED_TO = "Assigned To"
    RESOLVED = "Resolved"
