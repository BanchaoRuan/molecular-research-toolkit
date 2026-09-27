# Using molecule-image-prep

Use the subskill through the parent workflow that installed it. Provide images as attachments or an image-folder path.

## Start a task

```text
Use molecule-image-prep with these images.
Prepare the single-molecule review package.
```

The agent asks only about required information that is missing or ambiguous. Reply in ordinary conversation; already established values are reused.

## Include requirements you already know

The [packaged example](examples/example/README.md) uses this request:

```text
Use molecule-image-prep with example.png.
Name the task example.
Use prefix example, three digits, starting at example001.
There are no existing IDs to retain.
Process the five complete targets from left to right.
Preserve the fifth target's counterion and charge marks.
Add 12 pixels of white padding on every side without resizing.
```

For your own task, provide its name, numbering scheme, existing ID-to-molecule mapping if applicable, and cropping requirements. You can also identify a subset of targets or specify which surrounding labels to retain.

## Request a crop correction

```text
Adjust example002 so the complete oxygen label is visible.
Keep its ID and update the review package.
```

This illustrates how to request a correction for the same target. The original source image remains unchanged.

[Input image and checked results](examples/example/README.md) · [Agent workflow](SKILL.md)
