/**
 * Sample content for the two non-import entry paths.
 *
 * Product data, kept out of the component that renders it: the old
 * `EmptyState.tsx` carried a 27-line YAML literal inline, which is how a
 * presentational file ends up owning the shape of the product's data model.
 *
 * Every value here is placeholder-shaped on purpose. Section 7 forbids
 * fake-precise invented numbers in sample data, so the one metric in the
 * highlights reads as an example rather than as a measurement someone took.
 */

export const SAMPLE_YAML = `cv:
  name: Your Name
  email: you@example.com
  phone: "+1 415 555 2671"
  location: City, State
  sections:
    education:
    - institution: Your University
      area: Computer Science
      degree: Bachelor of Science
      start_date: 2018-09
      end_date: 2022-05
    experience:
    - company: Your Company
      position: Software Engineer
      start_date: 2022-06
      end_date: present
      location: City, State
      highlights:
      - Built and shipped production features using Python and TypeScript.
      - Cut API latency with caching and query optimization.
    skills:
    - label: Languages
      details: Python, TypeScript, SQL
    - label: Tools
      details: Docker, Git, FastAPI, React, PostgreSQL
`;

/** The tertiary path: the least that renders, to be filled in by hand. */
export const SKELETON_YAML = `cv:
  name: Your Name
  email: you@example.com
  sections:
    experience: []
`;
