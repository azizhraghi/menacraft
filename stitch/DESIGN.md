```markdown
# Forensic Intelligence Design System: Technical Documentation

## 1. Overview & Creative North Star
The creative North Star for this design system is **"The Digital Pathologist."** 

This system is designed to convey absolute authority, military-grade precision, and cold, analytical clarity. Unlike consumer-grade software that relies on friendly rounded corners and bright colors, this system utilizes a "Dark Lab" aesthetic. It moves beyond standard templates by employing intentional asymmetry, high-density data visualizations, and sophisticated glassmorphism. The goal is to make the investigator feel like they are looking through a high-powered digital microscope where every pixel is a piece of evidence.

### Breaking the Template
*   **Intentional Asymmetry:** Avoid perfectly centered layouts. Use "weighted" sidebars and staggered data grids to mimic the feel of a custom command center.
*   **Depth through Light:** Instead of lines, we use light. Glows and subtle gradients replace traditional borders to define the "active" zone of analysis.

---

## 2. Colors
Our palette is rooted in deep obsidian and cybernetic blues, designed for long-duration focus in low-light environments.

### The Palette (Material Design Mapping)
*   **Primary (Action/Focus):** `primary: #81ecff` (Cyber Blue) — Used for critical interaction points.
*   **Background:** `surface: #0d0e12` (Deep Charcoal) — The foundation of the "Dark Lab."
*   **Status Indicators:**
    *   **Authentic:** `tertiary: #c3ffcd` (Neon Green Glow)
    *   **Suspicious:** `secondary: #cfe6f2` (Warning Amber / Slate Shift)
    *   **Likely Synthetic:** `error: #ff716c` (High-Visibility Red)

### The "No-Line" Rule
Sectioning must **never** be achieved with 1px solid borders. Boundaries are defined through:
*   **Tonal Shifts:** Placing a `surface-container-high (#1e1f25)` card on top of a `surface-dim (#0d0e12)` background.
*   **Negative Space:** Using a strict 32px or 48px gap to separate analytical modules.

### Surface Hierarchy & Nesting
Treat the UI as layered sheets of obsidian glass. 
*   **Base:** `surface-container-lowest (#000000)` for the deepest background.
*   **Modules:** `surface-container (#18191e)` for primary analysis cards.
*   **Inner Scans:** `surface-container-highest (#24252b)` for nested data tables or code snippets.

### Signature Textures
Use a subtle linear gradient on primary CTAs: from `primary (#81ecff)` to `primary-container (#00e3fd)` at a 135-degree angle. This provides a "fuel-cell" glow that flat colors cannot replicate.

---

## 3. Typography
The system uses a high-contrast pairing of **Manrope** and **Inter**, with **Space Grotesk** reserved for technical metadata.

*   **Display (Manrope):** Large, bold headlines used for high-level findings. The wide character set of Manrope feels modern and authoritative.
*   **Headline & Title (Manrope):** Used for module titles. High contrast against the dark background ensures immediate legibility of the "Case File" name.
*   **Body (Inter):** The workhorse for forensic reports. Inter's tall x-height maintains clarity even at small sizes during dense data reviews.
*   **Labels (Space Grotesk):** Used for timestamps, coordinates, and "Forensic Intelligence" data strings. Its monospaced feel suggests machine-generated precision.

---

## 4. Elevation & Depth
In a forensic environment, depth equals importance. We achieve this through **Tonal Layering** rather than drop shadows.

### The Layering Principle
Stacking surfaces creates natural elevation. 
*   **Level 0:** `surface` (Background)
*   **Level 1:** `surface-container-low` (Navigation Rails)
*   **Level 2:** `surface-container` (Content Cards)
*   **Level 3:** `surface-bright` (Active/Hovered Elements)

### Ambient Shadows
For floating modals or tooltips, use a "Cyan-Tinted Shadow." 
*   **Value:** `0px 20px 40px rgba(0, 229, 255, 0.08)`
*   This mimics the light cast from a monitor, making the element feel part of the digital environment.

### The Ghost Border
If a separator is functionally required for accessibility, use a **Ghost Border**:
*   `outline-variant (#47484c)` at 15% opacity. It should be felt, not seen.

### Glassmorphism
For analysis overlays, use a background blur of `12px` combined with `surface-container-high` at 70% opacity. This "frosted lens" effect simulates a HUD (Heads-Up Display) overlaying the raw data.

---

## 5. Components

### Buttons
*   **Primary:** `primary` background with `on-primary` text. No radius (sharp) or `4px` (precise). 
*   **Secondary (Action):** Ghost style. `outline` border (15% opacity) with `primary` text.
*   **State:** On hover, apply a `primary_dim` outer glow (4px spread).

### Cards & Data Modules
*   **Rule:** Forbid divider lines. 
*   Separate header and body using a background shift from `surface-container-high` (header) to `surface-container` (body).
*   Use `sm (0.125rem)` or `md (0.375rem)` corner radius only. Rounded corners undermine the "military-grade" feel.

### Status Indicators (Forensic Tags)
*   Small, pill-shaped chips with a `10%` background opacity of the status color and `100%` opacity text.
*   **Authentic:** Text: `#c3ffcd` | BG: `rgba(195, 255, 205, 0.1)`
*   Add a `1px` inner glow to the 'Likely Synthetic' tag to make it vibrate visually as a high-priority warning.

### Technical Input Fields
*   **Resting:** `surface-container-lowest` background with a subtle bottom-only `outline-variant`.
*   **Focus:** The bottom border transforms into a `primary` glow.

---

## 6. Do's and Don'ts

### Do:
*   **Use Monospacing for Data:** Always use `Space Grotesk` for numbers, hashes, and timestamps.
*   **Embrace "Void" Space:** Let large areas of `surface-dim` exist to provide visual relief between complex data sets.
*   **Subtle Animation:** Use 300ms "ease-out" transitions for glass overlays to simulate a digital lens focusing.

### Don't:
*   **Don't use pure White:** Use `on-surface (#faf8fe)` to prevent eye strain.
*   **Don't use standard shadows:** Avoid black, muddy shadows. If an element needs lift, use a tinted ambient glow or a background color shift.
*   **Don't use large radii:** Never go above `md (6px)` for any component. Softness is the enemy of forensic precision.
*   **Don't use Dividers:** If you feel the need for a line, try using a `16px` vertical space increment instead.```