# GenAI Disclosure

This project was written with AI assistance.

- **Tool:** Hermes Agent (Nous Research desktop agent) using the
  `meta/muse-spark` model family.
- **Process:** The code was generated iteratively under the direction of
  the repository owner (Topher Sheridan), who specified the requirements,
  redirected design decisions (models, cookie persistence, per-section
  getters, BeautifulSoup parsing), and supplied portal credentials for
  live testing.
- **Verification:** The login flow, cookie handling, and parsers were
  exercised against the live Launtel residential portal, and the offline
  unit suite (`python3 -m unittest discover -s tests`) passes.
- **Review status:** AI-generated code should be treated as unreviewed
  until a human has read it. The owner accepts responsibility for the
  final content of this repository.

No customer data, passwords, or session tokens are stored in this
repository (see `.gitignore`).
