# Quickstart: a chatbot

1. **Install uv.** One line, the one [uv's installation page](https://docs.astral.sh/uv/getting-started/installation/) gives for the platform:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install the command.**

   ```bash
   uv tool install --python 3.12 ecosemantic
   ```

   `--python 3.12` has uv use a Python of 3.12 or newer, downloading one when the machine has only an older Python, as Debian 12 and macOS do.

3. **Connect your chatbot.** `ecosemantic init` writes this server into the MCP configuration of each chatbot it finds on the machine, and keeps every other server those files name.

   ```bash
   ecosemantic init                              # every chatbot found
   ecosemantic init --client claude-desktop      # or the ones you name
   ```

   With several found it asks which, at a terminal. It ends by saying to restart the chatbot, after which the EcoSemantic page opens in your browser; with none found it names Claude Desktop's download page and exits 1. VS Code keeps a configuration per workspace, which `init` does not find: `ecosemantic connect vscode --workspace path/to/project` writes it. `ecosemantic doctor` reports what the install holds: the interpreter, the solver, the data and systems directories, the installed databases, the page's address, and each chatbot's configuration.

4. **Restart the chatbot.** It starts the server over standard input and output. No page follows the server's events, so the server opens the page itself.

5. **Install a background database.** With none installed the page's welcome offers the sources a database installs from: USLCI, BAFU, ecoinvent, or an openLCA JSON-LD zip you hold. Pick one, enter an account or tick the terms when the source asks for either, and watch the install's steps. A person in a terminal takes the same step with `ecosemantic setup`, as [Getting a database](getting-a-database.md) says.

6. **Ask for a model.** For example: *"On ecoinvent-3.12-cutoff, model one bicycle frame of 2 kg of low-alloyed steel tube, with 8 % scrap as a parameter; calculate its climate change score and show the contribution by process."* The agent reads the guide on building a model, calls the tools, and every write lands in the product system's change log. The model lands on the page as it is built.

The page the server opens draws the model, shows its log and results, and takes your requests, which the agent answers. The agent gives you the page's address (`view_link`).

Product systems and installed databases live in two directories under your EcoSemantic folder: `%LOCALAPPDATA%\ecosemantic` on Windows, `~/Library/Application Support/ecosemantic` on macOS, `$XDG_DATA_HOME/ecosemantic` (`~/.local/share/ecosemantic`) on Linux, each holding `data` and `systems`. `--data-dir` and `--systems-dir` name others. The files a database installs from are downloaded into `downloads` in the data directory, unless `LCA_DATA_INTERFACE_CACHE` names another folder.
