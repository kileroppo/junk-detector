## Round 1: First-time User (初次使用者)
### Dao (Philosophy) - "少则得，多则惑" - The product must explain itself in one glance.
### Shu (Tactics) - "知己知彼" - Understand that new users have zero context; every term is foreign.
### Problems Found
1. [P1] Score form has no explanation of what the product does
2. [P1] Dashboard shows meaningless zeros when empty (confusing)
3. [P2] Nav links have no aria-labels for clarity
### Fixes
- Added value proposition hero text to score form
- Added empty state with CTA to dashboard
- Added aria-labels to all nav links
### Jobs Quote: "When you first walk in a store, does the staff explain what they sell, or do they make you guess?"

## Round 2: Busy Professional (忙碌的职场人)
### Dao (Philosophy) - "天下难事，必作于易" - Make the easy path the only path.
### Shu (Tactics) - "兵贵神速" - Speed is the only UX that matters when commuting.
### Problems Found
1. [P1] Submit button scrolls out of view on mobile after text entry
2. [P2] Touch targets below 44px on quick-score form
3. [P2] No swipe affordance hint on history cards
### Fixes
- Added sticky submit button on mobile
- Increased all input/button heights to 44px+
- Added swipe hint on first history card
### Jobs Quote: "If you have to think about how to use it, we failed."
