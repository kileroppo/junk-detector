## Round 3: Deep Researcher (深度研究者)
### Dao (Philosophy) - "大巧若拙" - True sophistication looks simple; power users need efficient, not complex.
### Shu (Tactics) - "因敌变化而取胜" - Adapt to how researchers actually work: search first, filter second.
### Problems Found
1. [P1] No text search in history - researchers can't find specific articles
2. [P2] Pagination shows no context (total pages, position)
3. [P2] No keyboard shortcut for search
### Fixes
- Added text search field to history filter bar
- Improved pagination with total pages and position info
- Added 'S' keyboard shortcut for search focus
### Jobs Quote: "The best interface for a researcher is one that gets out of the way."

## Round 4: Retired Elderly (视力退化的长辈)
### Dao (Philosophy) - "见素抱朴" - Return to simplicity; clarity is kindness.
### Shu (Tactics) - "先为不可胜" - First ensure no one is excluded, then optimize for power.
### Problems Found
1. [P1] No font size adjustment - small text is unreadable for aging eyes
2. [P1] text-gray-500 fails WCAG AA contrast on dark backgrounds
3. [P2] Score dimension numbers hidden when bars are small
4. [P2] Help button and hamburger menu below 44px touch targets
### Fixes
- Added 3-level font size toggle (16/18/20px) with localStorage
- Fixed all content text-gray-500 to text-gray-400 for 5.6:1 contrast
- Always show dimension score numbers regardless of bar width
- Increased touch targets to 44px minimum
### Jobs Quote: "Accessibility isn't a feature. It's a sign of respect."
