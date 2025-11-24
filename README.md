# UI-State-Capture

A generalizable system for runtime UI workflow capture across arbitrary web applications

This project implements an autonomous agent that navigates live web apps, executes user-requested tasks, and captures all intermediate UI states in real time. It is designed for multi-agent systems where one agent provides high-level natural language instructions and another agent executes them inside a browser without prior knowledge of the workflow.

The system outputs a structured workflow dataset with screenshots, metadata, actions, and timing for each step.

---

## Features

### Generalizable Cross-App Task Execution

Works across Linear, Notion, and similar tools without any app-specific hardcoding.

### Automatic UI State Capture

Each step captures:

* Screenshot
* URL
* Page title
* Action metadata
* Timestamps
* Success/error flags

### Handles Non-URL Transitions

Detects and logs modals, dropdowns, and transient views even when the URL stays the same.

### Login Detection and Pause

If login or authentication is required, the system pauses and waits for the user to log in before resuming.

### Structured Workflow Dataset

Each run is saved to:

```
ui_dataset/
  timestamp_app_task/
    step_001.png
    step_002.png
    workflow.json
```

### Multi-Task Execution in a Single Browser Session

A shared browser session executes sequential tasks for efficiency and context continuity.

---

## How It Works

### 1. Task Interpretation

A natural language instruction is converted into a structured task with constraints such as:

* Stay within the app domain
* Never navigate outside
* Only use UI interactions
* Stop if login is needed

### 2. Agent Control Loop

At every step:

* The LLM chooses a browser action based on the UI
* Metadata is recorded
* Screenshots and timestamps are logged
* State is saved to the workflow

### 3. Human-in-the-Loop Login Handling

Automating login flows across SaaS apps like Notion, Linear, or GitHub was brittle and unnecessary. Instead, the system:

* Detects when the agent encounters a login page
* Pauses execution
* Prompts the user to authenticate manually
* Resumes once ready

### 4. Workflow Generation

The final JSON log contains:

* All steps
* Browser actions
* DOM/text context
* Time per action
* Screenshot paths
* Success/failure summary

---

## Example Tasks Tested

### Linear

* Create a project
* Filter issues
* Delete a project

### Notion

* Create a database
* Remove a database

These workflows were not hardcoded; the agent discovers them dynamically at runtime.

---

## Reliable UI State Capture

Multiple capture strategies were tested:

* URL-based state detection
* Perceptual image diffing
* DOM mutation detection
* Multi-moment captures
* Hashing to reduce duplicates

After testing, the most dependable approach was:

**Capture a screenshot immediately after each agent action**, because the agent’s step boundaries naturally align with UI transitions. Alternative methods produced inconsistent or missed captures.

---

## Running the System

### 1. Set Environment Variables

```
export GOOGLE_API_KEY=your_key_here
```

### 2. Run the Program

```
python main.py
```

### 3. Log in Manually When Prompted

The agent will automatically pause if authentication is required.

---

## Project Structure

```
main.py                     # Orchestrates multi-task execution
execute_task()              # Runs one task and builds workflow dataset
capture_hooks/              # Per-step logging and screenshot capture
schemas/                    # Pydantic schemas for dataset
login_detection/            # UI/URL heuristics for login detection
ui_dataset/                 # All output workflows
```

---

## Purpose

This system demonstrates:

* Autonomous UI navigation
* Dynamic workflow reconstruction
* Generalization across complex apps
* Dataset creation for LLM agent training
* Resilient handling of real-world UI constraints

It provides a foundation for training or evaluating UI agents that must reason about unfamiliar web interfaces.

---

## What I Would Improve With More Time

This project prioritizes end-to-end functionality across real apps, but there are several areas I would extend to bring it closer to production-level robustness.

### 1. Stronger Generalization

Currently, the system works across multiple apps without hardcoding, but a proper abstraction for UI states combining DOM structure, semantic cues, and vision signals which would make it easier to scale to new apps and reduce reliance on screenshot-after-action logic.

### 2. Improved State-Change Detection

I experimented with perceptual diffing, hashing, DOM mutation checks, and multi-moment sampling. With more time, I would implement a hybrid signal that clusters “meaningfully different” UI states and filters out noise, reliably detecting modal openings, navigation shifts, success banners, and form transitions even when the URL doesn’t change.

### 3. Better Observability and Debugging

Adding a lightweight timeline view that shows each step, the action taken, and why the system considered that step a new state would make debugging easier and help diagnose edge cases like delayed renders, spinners, and multi-stage modals.

### 4. Principled Workflow Engine

Introducing a small state graph linking actions, UI observations, and transitions would allow the system to avoid loops, recognize repeated states, and produce cleaner workflow datasets.

### 5. Richer Dataset Metadata

The current dataset is fully structured and consistent, but adding additional metadata—latency per action, DOM node diffs, semantic descriptions—would make it even more valuable for training downstream UI agents.

