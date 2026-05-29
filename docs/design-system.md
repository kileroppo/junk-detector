# Design System

Visual identity and component patterns for the junk-detector project across all surfaces (CLI, Chrome Extension, API).

## Color Palette

### Primary Colors

| Name    | Hex       | Usage                              |
|---------|-----------|------------------------------------|
| Green   | `#10B981` | Quality content, positive signals  |
| Amber   | `#F59E0B` | Suspicious content, warnings       |
| Red     | `#EF4444` | Junk content, danger signals       |

### Neutrals

| Name       | Hex       | Usage                          |
|------------|-----------|--------------------------------|
| Gray 900   | `#1F2937` | Primary text                   |
| Gray 700   | `#374151` | Secondary text, icon strokes   |
| Gray 500   | `#6B7280` | Muted text, descriptions       |
| Gray 300   | `#D1D5DB` | Borders, dividers              |
| Gray 100   | `#F3F4F6` | Backgrounds, tags              |
| White      | `#FFFFFF` | Surface backgrounds            |

### Legacy Colors (Extension badge)

| Name    | Hex       | Usage               |
|---------|-----------|---------------------|
| Green   | `#34C759` | Badge OK            |
| Orange  | `#FF9500` | Badge caution       |
| Red     | `#FF3B30` | Badge junk          |

## Typography

System font stack across all surfaces:

```
-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif
```

### Sizes

| Context            | Size   |
|--------------------|--------|
| Popup heading      | 48px   |
| Body text          | 14px   |
| Score value        | 28px   |
| Labels/tags        | 12px   |
| Hints              | 10-11px|

## Emoji Conventions

Consistent emoji usage across CLI, extension, and API responses:

| Verdict    | Emoji | Chinese Label    |
|------------|-------|------------------|
| Quality    | ✅    | 优质 / 正常       |
| Suspicious | ⚠️    | 可疑 / 需要注意    |
| Junk       | 🚨    | 垃圾 / 高风险     |
| Unknown    | ❓    | 未知              |
| Loading    | ⏳    | 检测中            |

### Supplementary Emoji

| Context        | Emoji |
|----------------|-------|
| Score results  | 📊    |
| Positive dims  | 📈    |
| Risk dims      | ⚠️    |
| Labels         | 🏷️    |
| Summary        | 💬    |
| Explanation    | 📝    |
| Tip/hint       | 💡    |

## Component Patterns

### CLI Panel (Rich)

Score verdicts use `rich.panel.Panel` with colored borders:

- Border color maps to verdict (green/amber/red)
- Large emoji as first visual element
- One-line explanation inside
- Evidence quotes in muted style
- Small score badge at bottom

### Extension Popup

- Centered layout, 280px width
- Verdict icon (48px emoji)
- Collapsible details section with keyword tags
- Educational "why" section with amber accent border

### Extension Icons (Eye Motif)

Three states representing "seeing through deception":

- `eye-green.svg`: Calm, open eye - content is trustworthy
- `eye-amber.svg`: Slightly narrowed eye - content is suspicious
- `eye-red.svg`: Alert, wide eye with radiating lines - content is dangerous

### Badge

- Numeric risk score displayed on extension icon
- Background color matches verdict
- Empty text for clean content (score = 0)

### Onboarding Page

- Centered card layout with subtle shadow
- Brand colors in bottom dot indicators
- Single CTA button in primary green
- Site list as rounded pill tags

## Spacing

| Token   | Value |
|---------|-------|
| xs      | 4px   |
| sm      | 8px   |
| md      | 16px  |
| lg      | 24px  |
| xl      | 32px  |
| 2xl     | 48px  |
