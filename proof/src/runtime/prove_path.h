#ifndef PROVE_PATH_H
#define PROVE_PATH_H

#include "prove_runtime.h"
#include "prove_string.h"

Prove_String *prove_path_join(Prove_String *base, Prove_String *part);
Prove_String *prove_path_parent(Prove_String *path);
Prove_String *prove_path_name(Prove_String *path);
Prove_String *prove_path_stem(Prove_String *path);
Prove_String *prove_path_extension(Prove_String *path);
bool          prove_path_absolute(Prove_String *path);
Prove_String *prove_path_normalize(Prove_String *path);

#endif /* PROVE_PATH_H */
