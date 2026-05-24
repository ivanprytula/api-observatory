---
name: html-css-standards
description: "Apply to: frontend HTML and CSS files (src/components/**/*.html, **/*.css). Enforces semantic HTML, accessibility, responsive design, and maintainable CSS."
applyTo: "**/*.html, **/*.css, src/**/*.css"
---

# HTML & CSS Standards

## HTML Best Practices

### Semantic HTML
Use semantic tags for better accessibility and SEO:
```html
<!-- Good: semantic structure -->
<header>
  <nav>
    <menu>
      <li><a href="/home">Home</a></li>
      <li><a href="/docs">Docs</a></li>
    </menu>
  </nav>
</header>

<main>
  <article>
    <h1>Scenario: Monolith Scaling</h1>
    <section>
      <h2>Learning Objectives</h2>
      <p>Understand vertical vs horizontal scaling.</p>
    </section>
  </article>
</main>

<!-- Bad: div soup, no semantic meaning -->
<div>
  <div>Navigation</div>
  <div>
    <div>Home</div>
    <div>Docs</div>
  </div>
</div>
```

### Accessibility (A11y)
- Always include `alt` text for images.
- Use proper heading hierarchy (H1 → H2 → H3, no skipping).
- Ensure sufficient color contrast (WCAG AA minimum 4.5:1).
- Use `aria-label` for icon buttons.
- Link text should be descriptive (`Learn more` ✓, `Click here` ✗).

```html
<!-- Good accessibility -->
<img src="architecture-diagram.png" alt="System architecture with microservices">
<button aria-label="Toggle navigation menu">☰</button>
<a href="/docs/setup">View setup guide</a>

<!-- Poor accessibility -->
<img src="diagram.png">
<button>☰</button>
<a href="/docs/setup">Click here</a>
```

### Meta Tags & SEO
```html
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="Learn distributed systems through hands-on Docker scenarios">
  <meta name="keywords" content="architecture, distributed systems, docker">
  <title>data-pipeline-async</title>
</head>
```

---

## CSS Best Practices

### Methodology: BEM (Block Element Modifier)
```css
/* Block: independent component */
.card { }

/* Element: part of a block */
.card__header { }
.card__title { }
.card__body { }

/* Modifier: variant of a block or element */
.card--featured { }
.card__title--large { }
```

### Selectors
- **Prefer classes**: Use `.class` over element selectors (`div`) or IDs.
- **Avoid nesting**: Keep specificity low; don't nest more than 2-3 levels.
- **Organize logically**: Group related rules, use comments for sections.

```css
/* ✓ Good: specific, reusable, low specificity */
.button {
  padding: 0.75rem 1.5rem;
  border-radius: 0.25rem;
  font-size: 1rem;
}

.button--primary {
  background-color: #007bff;
  color: white;
}

.button--large {
  padding: 1rem 2rem;
  font-size: 1.25rem;
}

/* ✗ Bad: high specificity, hard to override */
div > p.text > .content > button#submit {
  /* ... */
}
```

### Responsive Design
Use mobile-first approach with media queries:
```css
/* Default: mobile */
.container {
  width: 100%;
  padding: 1rem;
}

/* Tablet and up */
@media (min-width: 768px) {
  .container {
    width: 750px;
    margin: 0 auto;
  }
}

/* Desktop and up */
@media (min-width: 1024px) {
  .container {
    width: 960px;
  }
}
```

### CSS Variables (Custom Properties)
```css
:root {
  --color-primary: #007bff;
  --color-error: #dc3545;
  --spacing-unit: 1rem;
  --font-family-sans: "Segoe UI", Roboto, sans-serif;
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.button {
  padding: var(--spacing-unit);
  background-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.error-message {
  color: var(--color-error);
}
```

### Flexbox & Grid
Prefer modern layout techniques over floats:
```css
/* Flex: 1D layout */
.navbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

/* Grid: 2D layout */
.dashboard {
  display: grid;
  grid-template-columns: 1fr 2fr 1fr;
  gap: 2rem;
}

@media (max-width: 1024px) {
  .dashboard {
    grid-template-columns: 1fr;
  }
}
```

---

## Common Patterns

### Cards
```html
<div class="card">
  <img src="scenario.png" alt="Scenario thumbnail" class="card__image">
  <div class="card__body">
    <h3 class="card__title">Monolith Scaling</h3>
    <p class="card__description">Learn how to scale from single server to distributed system.</p>
    <a href="/scenarios/1" class="card__link">Explore</a>
  </div>
</div>
```

```css
.card {
  border-radius: 0.5rem;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  transition: transform 0.2s, box-shadow 0.2s;
}

.card:hover {
  transform: translateY(-0.25rem);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.card__body {
  padding: var(--spacing-unit);
}

.card__title {
  margin-top: 0;
  font-size: 1.25rem;
}

.card__link {
  display: inline-block;
  margin-top: var(--spacing-unit);
  color: var(--color-primary);
  text-decoration: none;
  font-weight: 600;
}

.card__link:hover {
  text-decoration: underline;
}
```

---

## Performance

### Critical CSS
Inline critical CSS above the fold:
```html
<head>
  <style>
    /* Critical CSS for above-the-fold content */
    body { font-family: var(--font-family-sans); }
    .header { background: var(--color-primary); }
  </style>
  <link rel="stylesheet" href="/css/main.css">
</head>
```

### Minimize HTTP Requests
- Combine multiple CSS files into one.
- Use CSS variables instead of SCSS for simplicity.
- Defer non-critical stylesheets with `media="print"` or JavaScript.

---

## Linting & Formatting

### Recommended Tools
- **Stylelint**: Catch CSS errors and enforce conventions.
- **Prettier**: Auto-format HTML and CSS.

### `.stylelintrc.json`
```json
{
  "extends": ["stylelint-config-standard"],
  "rules": {
    "selector-class-pattern": "^[a-z]([a-z0-9-]*)?(__[a-z0-9]([a-z0-9-]*)?)?$",
    "max-nesting-depth": 3,
    "declaration-no-important": true
  }
}
```
