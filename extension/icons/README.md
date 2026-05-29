# Extension Icons

This directory contains SVG source icons for the Chrome extension.

## Icon States

- `icon-green.svg` - Green checkmark circle (content is quality)
- `icon-yellow.svg` - Yellow/orange warning triangle (content is suspicious)
- `icon-red.svg` - Red alert circle (content is junk)
- `icon-gray.svg` - Gray neutral circle (default/unscored state)

## Required PNG Files

Chrome requires PNG icons in specific sizes for the manifest. Generate PNGs from the SVGs:

- `icon-gray-16.png` - 16x16px (toolbar icon)
- `icon-gray-48.png` - 48x48px (extensions page)
- `icon-gray-128.png` - 128x128px (Chrome Web Store)

You can generate these using ImageMagick or any SVG-to-PNG converter:

```bash
# Using ImageMagick
for size in 16 48 128; do
  convert -background none icon-gray.svg -resize ${size}x${size} icon-gray-${size}.png
  convert -background none icon-green.svg -resize ${size}x${size} icon-green-${size}.png
  convert -background none icon-yellow.svg -resize ${size}x${size} icon-yellow-${size}.png
  convert -background none icon-red.svg -resize ${size}x${size} icon-red-${size}.png
done
```

## Notes

- The default icon (gray) is referenced in manifest.json
- The background script dynamically changes the badge color based on scoring results
- SVGs are provided as design source files; the extension uses PNG references
