# Security and Operating Model

Roles: business requester/consumer, business owner, technical owner, data steward, BI/platform administrator, governance administrator and approver.

Business owner is accountable for purpose and value; technical owner maintains report/model; data steward owns data meaning/quality; platform/governance defines standards and access; approver authorises lifecycle decisions.

Enforce permissions in backend and integration boundaries, not only UI. Separate request, edit, approve, publish and retire permissions. Record audit events. Use synthetic users/roles for the hackathon; do not claim production SSO unless implemented and tested. Do not use real Bayer, patient, employee or customer data without authorisation.
