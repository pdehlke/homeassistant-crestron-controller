# Finding your touch panel's project file

Your Crestron touch panels already hold a complete list of the
[joins](../concepts/glossary.md#join) your system uses, with the label a person sees next to each
one. It is the panel's project file. Reading it is the safest way to start an inventory, because it
names joins without pressing anything. This page walks you through finding that file in your own
house, step by step, from not knowing which box is which to having the file on your computer.

[Panel project files](./panel-project-files.md) is the reference for the two commands that fetch
and read the file. This page is the part before that: working out which panel to ask, whether it
has a file the tool can read, and where on the panel that file lives.

You need the `crestron-controller` command-line tool, installed as described in
[installing](../getting-started/installing.md#the-command-line-tool), and a computer on the same
network as the panels. Nothing on this page changes anything on a panel or a processor. Addresses
such as `10.0.0.31` are examples; use your own.

## What you are looking for

A [touch panel](../concepts/glossary.md#touch-panel) does not decide what its buttons do. The
[control processor's](../concepts/glossary.md#control-processor) program does that. But the panel
has to know what to draw, so the installer loaded a project onto it: every page, every button,
every label and every join number. The installer designed that project in Crestron's VT Pro-e
software and compiled it for the panel.

On the TSW x52 family of panels (the TSW-552, TSW-752, TSW-1052 and related models), the compiled
project is stored on the panel as an XML file called `Environment.xml`. That is the file you want.
Its name is the same on every x52 panel; what is inside it is specific to your house.

The project the installer gave the panel also has a name of its own, chosen by the installer. It
often names the job and the panel model, but there is no rule. You do not need to know that name in
advance. The steps below find it.

## Step 1: find the panel's network address

You need the address of a touch panel, not the processor. This is the one place in the whole
inventory where you talk to a panel directly; everything else talks to the processor.

Ways to find it, easiest first:

- **Your router's client list.** Look for devices the router attributes to Crestron. Processors and
  panels both appear there. Write down every Crestron address you find.
- **The panel's own setup screens.** Most panels have an on-screen setup area that shows the
  panel's own address and the processor it talks to. How to reach it varies by model and firmware,
  so check the panel's documentation. Setup screens can change settings as easily as show them, so
  look and do not touch.
- **The processor's `WHO` command.** `crestron-controller console 10.0.0.20 WHO`, pointed at the
  processor, lists the clients connected to it right now with their addresses. A touch panel that
  is switched on and working will be among them.

## Step 2: confirm it is a panel, and which model

Several Crestron addresses can look alike in a router list. Ask each one what it is. Panels run the
same plain-text [CTP console](../concepts/glossary.md#ctp-console) that processors do, on port
41795:

```sh
crestron-controller console 10.0.0.31 --port 41795 VER
```

The reply names the model and firmware. If it names a TSW-552, TSW-752, TSW-1052 or another x52
model, carry on. If it names a processor (for example a CP3, an MC3 or an MC2E, or an audio
product with a processor built in), you have the wrong box; try the next address. You can also turn
the panel around: the model is printed on a label on the back.

If the panel names a newer family, such as an x60 or x70 model, stop here. Those panels run HTML5
projects packed in a different format, which the parser does not read yet. See
[formats that are not supported](./panel-project-files.md#formats-that-are-not-supported).

If nothing answers on port 41795, try port 23 with the same command and no `--port`. A panel that
answers on 23 but not 41795 will not be able to send its file, because the transfer only works on
41795. See [the CTP console and file
retrieval](../protocol/ctp-console-and-file-retrieval.md#fetching-a-file-with-xgetfile).

While you are connected, it is worth checking which processor the panel belongs to:

```sh
crestron-controller console 10.0.0.31 --port 41795 IPTABLE
```

On the TSW-752 panels this project was developed against, the panel's table listed exactly one
entry: the processor it registers with, and the [IP-ID](../concepts/glossary.md#ip-id) it
registers as. The project file you are about to fetch describes buttons on that processor's
program, so this tells you which processor its joins belong to.

## Step 3: ask the panel which project it is running

```sh
crestron-controller console 10.0.0.31 --port 41795 PROJECTINFO
```

On the panels this was developed against, this reported the project's name and when it was loaded
onto the panel. It is a cheap way to answer the next question without a ten-minute download.

### If you have more than one panel

Run `PROJECTINFO` on every panel and compare. Two panels that report the same project name and
version are running the same project, and one download covers both. On the system this project
came from, every panel of the same model ran the same project, so one fetch was enough.

Do not assume that in your house. An installer can give each panel its own project, for example a
kitchen panel with different pages from a bedroom panel, and panels of different models will
always have different projects. Fetch one file for each distinct project you find.

## Step 4: find the file on the panel

The file is normally at `\display\swf\Environment.xml`. Check before you start a long download, by
listing the panel's folders:

```sh
crestron-controller console 10.0.0.31 --port 41795 'DIR \display'
crestron-controller console 10.0.0.31 --port 41795 'DIR \display\swf'
```

Keep the single quotes. Your shell treats a backslash as special, and without the quotes the panel
would receive `DIR display` and answer about the wrong folder. The quotes are removed by the shell
before anything is sent, so the panel sees the path exactly as Crestron writes it.

On a TSW-752, the two listings looked like this:

```text
DIR \display        ->  <your project name>.vtx, swf\
DIR \display\swf    ->  Environment.xml
```

The `.vtx` file in `\display` carries the project's name, so it is a second way to see which
project the panel runs. It is not the file the parser reads. `Environment.xml` inside `swf` is the
project as readable XML, and its size in the listing tells you how long the download will take:
roughly a megabyte every three to four minutes.

If `Environment.xml` is somewhere else on your panel, note the full path and pass it to the fetch
command with `--remote-path`. Quote it the same way:
`--remote-path '\some\other\path\Environment.xml'`. If there is no `Environment.xml` anywhere, the
panel is probably not an x52 model, and the parser will not have a file it can read.

## Step 5: fetch it and read it

```sh
crestron-controller panel fetch 10.0.0.31 -o Environment.xml
crestron-controller panel parse Environment.xml -o draft.yaml
```

The first command downloads the file, which on a TSW-752 with a 3.5 MB project took about twelve
minutes. The panel keeps working normally while it sends. The second command reads the file on your
computer, without touching the network, and writes a draft [join map](../concepts/glossary.md#join-map)
in which every entry is read-only.

Both commands, their options, their error messages and how to read the draft are covered in
[panel project files](./panel-project-files.md). Read its section on ["also
appears as"](./panel-project-files.md#also-appears-as-and-why-it-matters-for-safety) before you
promote anything in the draft to something Home Assistant can switch. That section is how you spot
a join the program shares with an alarm keypad.

## When the panel cannot give you a file

| What happened | What to do |
| --- | --- |
| The panel is an x60, x70 or other newer model | The parser cannot read its project yet. Use [`listen`](./listening-to-a-processor.md) and [`watch`](./watching-keypads.md) instead. |
| `VER` answers but `PROJECTINFO` or `DIR` is refused | The firmware may name these differently or block them. Try the same command on port 23 to compare, then fall back to `listen` and `watch`. |
| The console asks for a login | Pass `--username`, as described in [the processor console](./processor-console.md#logging-in). That path has not been tested against a real panel. |
| The fetch stops partway | Nothing is written. Run it again. See [when it fails](./panel-project-files.md#when-it-fails). |
| Your installer gave you a `.vtz` file | That is a VT Pro-e source project, a packed archive, and the parser refuses it. Fetching from the panel gets you the readable form. |

None of these stops you from building an inventory. The project file only adds names and finds
joins the processor has not mentioned yet; [taking an inventory](./inventory-overview.md) shows how
the other tools fill in the rest.

## Keep it private

The project file and the draft made from it describe your house in detail: every room, every
controllable load, and the alarm keypad's page. Keep them on your own computer and out of any public
repository, forum post or issue.
