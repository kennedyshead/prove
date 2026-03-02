# Linter errors

Prove is by definition a hard language to learn with many new concepts (and existing ones) that sometimes needs some explenation to make sense. This means that linting/formatting/checks are super important! Lets aim to guide the developer to write great and consistant code.
Some Errors (Like ducktype variable decleration) can actually be solved in a format command, this is a first GOTO for the linter. When this behaviour is adapted we should add an info message explaing how a proper version of the code would look and a text about this being fixed by the formatter/build automagically so the compiler will pass even though its not proper praxis.

## Rules

- 0 Messages should ideally read as normal english sentences, for example "pure function cannot call IO function '{fname}'" This would not be expressed in this way if you explained it to a fellow programmer.
- 1 We should try to not be disruptive as much as possible! This means the only errors allowed are when something actually will not compile!
  - 1.1 That said, we should not adapt the compiler to this rule, if something is needed for efficiency or for the code to compile it should have a a clear error!
- 2 lint rules are meant to help the developer, they need to be clear to what is wrong (in natural understandable english, technical yargong where needed). 
  - 2.1 And they also need a solution to the problem presented!
    - 2.2 This can be skipped for non-trivials like "tabs are not allowed, use spaces" those are enough as is
  - 2.2 If its possible to present solution by code example (with actual names from the problematic scope) that is the prioritized solution. 
  - 2.3 If its not possible to present by code we need to 
  - 2.4 All linting messages should(if not possible this needs to be documented in the code) link to the actual documentation (https://prove.botwork.se) 
    - 2.3.1 as these links and the documentation needs to match we need a way to make sure that they are correct before commit. (pre-commit hook should check this).
- 3 Syntax error making reading the rest of the file/problems unreadable: in this case LSP should only report one error on the line where the syntax seems to fail. If we know the actual error we should follow the rules. If we cant figure out the actual syntax failing this should be considered a bug and a link to our issue system should be added: https://code.botwork.se/Botwork/prove/issues
- 4 Warnings should be used for anything that can compile but would be far better with adding/removing something. This is meant for problems that would be better code (boundries, pre/post requirements) both for compiler and the developer.
- 5 Info should be used for any other feature we have that dont fit warning/error

E200 Should be for the module declaration only. 

A new info message should be added for narrative. 
The text for the info message should be consise but informative to how to add it 
and what the developer actually will gain by doing so.

## Definitions
* There are only duplicate check so far. Lets also add rules to not declare builtins and other rules that would break the compiler.
* Needs to be unique per type/verb/module/function/import/keyword (that only support one or have a upper limit to how many).
  - E301 We should add line references for this! Maybe even a short excerpt so the LSP can be more informative
    - IMPORTANT As we can define multiple functions differented by only the verb we need to check that the function name is actually only decleared one time for the verb rather than for the actual function name.

  - E302 Would this not be the same as E301? what is the differencs? Line and excerpt applies here to.

## Types
* The current ones are quite cryptic! We need to follow the rules! Are we covering all the actual errors/warnings/info messages?

## Function & Calls
* E310 and E300 And other undefined: lets be specific here and create one per type, that way we can be more informative about why and how to solve it + link to documentation about why things work in a certain way.

## Field Access
* E340 Isnt this also a version of an undefined?

## Verb enforcement
* We need to follow the rules 

