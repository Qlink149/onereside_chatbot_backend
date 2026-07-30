# Changelog

All notable changes to OneReside Bot are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<img src="assets/hue-bar.svg" width="100%" height="4" alt=""/>

## [2026-07-30]
_Author: Pratham Paleriya_

### Concierge — handling unclear messages

#### Changed
- **A word that could mean two things now gets a question, not a guess.** When
  someone sends a term that could mean either the item itself or a brand that
  specialises in it — "artifact", "rugs", "lighting" — the concierge asks which
  one they're after and waits for the answer. Previously a message like
  "artifact" got a brand recommendation straight away, even when the customer
  was looking to browse products.
- **The One Reside concierge now runs on a reasoning model**, matching the
  product and service agents. Replies take a little longer in exchange for more
  careful handling of vague or unusual messages.

#### Fixed
- **Unreadable messages no longer get a confident brand recommendation.** Brand
  search always returns its closest matches, so a typo or a few stray characters
  ("shior") came back with a real brand presented as though it were what the
  customer meant. The concierge now has to check that a result genuinely matches
  what was asked before naming it, and to ask the customer to repeat themselves
  when a message can't be read at all.

### Users — delete user

#### Changed
- **Delete entries in the activity log now record how many messages were
  removed**, alongside the phone number and username.

#### Fixed
- **Deleted users no longer leave their chats behind.** Deleting a user removed
  them from the users list but left their whole conversation sitting in the
  messages section, so a "deleted" person's chat could still be opened and read
  there. Deleting a user now clears the profile and the complete message
  history together. Orders, enquiries and payments are business records and are
  still kept.
- **A failed delete no longer half-removes a user.** If the cleanup can't
  finish, the user now stays in the list so the delete can simply be run again,
  instead of vanishing from the list while their messages remain behind.

## [2026-07-22]

### Added
- `DELETE /system/users/{user_id}` to delete a user's profile (orders/payments are preserved).
- Admin activity logging, backed by a new `admin_logs` collection.
- `GET /system/admin-logs` to list admin activity logs.
