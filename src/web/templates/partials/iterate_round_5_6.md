## Round 5: Non-native Language User (非母语使用者)
### Dao (Philosophy) - "道可道，非常道" - If a term needs translation, it shouldn't be there in the first place. Use universal concepts.
### Shu (Tactics) - "因敌变化而取胜" - Adapt language to the user's level, not the developer's vocabulary.
### Problems Found
1. [P1] Technical jargon (Thunder, Dispatcher, Token ROI) unexplained
2. [P2] Batch tab lacks clear instructions for non-tech users  
3. [P2] Confidence factors show raw English dimension keys
### Fixes
- Added title tooltips explaining all technical terms in Chinese
- Added clear helper text for batch URL input
- Mapped English dimension keys to Chinese labels in result template
### Jobs Quote: "Eliminate jargon. If your grandmother can't understand it, rewrite it."

## Round 6: Accessibility User (无障碍使用者)
### Dao (Philosophy) - "上善若水，水利万物而不争" - True design serves everyone equally without drawing attention to itself.
### Shu (Tactics) - "善用兵者，无智名，无勇功" - The best accessibility is invisible; it just works.
### Problems Found
1. [P0] Tab component has zero ARIA semantics - screen readers can't navigate
2. [P0] Mobile menu button missing aria-expanded state
3. [P1] Toast notifications invisible to screen readers (no aria-live)
4. [P1] Table rows use onclick without keyboard alternative
5. [P2] Theme toggle lacks role="switch" semantics
### Fixes
- Added full ARIA tab pattern (tablist, tab, tabpanel, aria-selected)
- Added aria-expanded toggling on mobile menu
- Added aria-live="polite" and role="status" to toast container
- Added role="link", tabindex="0", and Enter key handler to table rows
- Added role="switch" and aria-checked to theme toggle
### Jobs Quote: "Design is not just what it looks like. Design is how it works - for everyone."
