# Agent skills

bevel ships four [Agent Skills](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills)
(`SKILL.md` folders) distilled from real print projects:

| skill | when |
|---|---|
| `bevel-part-authoring` | writing/editing `src/<part>.py`; CadQuery/OCC pitfalls reference |
| `bevel-render-verify` | the render → inspect → look loop and acceptance checklist |
| `bevel-model-iteration` | changing a model safely: config layers, comparable runs, notes |
| `bevel-mcp-workflow` | driving bevel through the MCP server |

```bash
bevel skills list
bevel skills install --project     # <project>/.claude/skills/   (bevel create does this by default)
bevel skills install --user        # ~/.claude/skills/
bevel skills path                  # where the bundled copies live
```
