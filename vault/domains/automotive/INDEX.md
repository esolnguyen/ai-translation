---
id: automotive-index
status: approved
domain: automotive
---

# Automotive domain

Notes extracted from three starter PDFs under `sources/automotive/`:

- `toyota-corolla-wikipedia.pdf` — model history, generations, variants, production
- `toyota-tsb-corolla-cross-2024.pdf` — Pre-Delivery Service procedures
- `bosch-brakes-catalogue.pdf` — braking-system architecture and components

## Review queue (this domain)

```dataview
TABLE confidence, status, tags, file.mtime as "modified"
FROM "domains/automotive"
WHERE status = "needs-review"
SORT confidence ASC, file.mtime DESC
```

## Notes

### Toyota Corolla — model knowledge

- [[corolla-overview]]
- [[corolla-generations]]
- [[corolla-regional-variants]]
- [[corolla-production-locations]]

### Pre-Delivery Service (2024 Corolla Cross / Cross HV)

- [[pre-delivery-service]]
- [[dc-cut-fuse]]
- [[pds-body-installation]]
- [[pds-system-initialization]]

### Braking systems (Bosch aftermarket)

- [[braking-system-architecture]]
- [[brake-pads]]
- [[brake-shoes]]
- [[brake-discs]]
- [[wheel-cylinders]]
- [[brake-fluid]]
- [[master-cylinder-and-booster]]
