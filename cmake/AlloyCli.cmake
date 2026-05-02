# AlloyCli.cmake — CMake entry point for alloy-cli projects.
#
# Usage from a project's CMakeLists.txt:
#
#     find_package(Python3 REQUIRED COMPONENTS Interpreter)
#     include(${ALLOY_CLI_CMAKE_DIR}/AlloyCli.cmake)
#     alloy_cli_init()
#     # … now ALLOY_PROJECT_NAME, ALLOY_BOARD_ID (or ALLOY_CHIP_*), etc. exist.
#     alloy_cli_link(my_target)
#
# This file is intentionally minimal: the heavy lifting (parsing TOML,
# validating the schema) lives in Python — see
# ``src/alloy_cli/cmake_bridge.py``.  Keeping CMake out of TOML parsing
# is the whole reason the bridge exists.

if(DEFINED _ALLOY_CLI_CMAKE_INCLUDED)
  return()
endif()
set(_ALLOY_CLI_CMAKE_INCLUDED TRUE)

# ----------------------------------------------------------------------------
# alloy_cli_init([PROJECT_DIR <dir>])
#
# Reads ``alloy.toml`` from ``PROJECT_DIR`` (default: ``CMAKE_SOURCE_DIR``)
# via ``python -m alloy_cli.cmake_bridge`` and exposes the parsed
# values as CMake variables in the caller's scope:
#
#   ALLOY_PROJECT_NAME           — project name
#   ALLOY_PROJECT_ALLOY          — pinned alloy version (may be empty)
#   ALLOY_PROJECT_ALLOY_CODEGEN  — pinned alloy-codegen version (may be empty)
#   ALLOY_BOARD_ID               — board id, when [board] is set
#   ALLOY_CHIP_VENDOR            — chip vendor, when [chip] is set
#   ALLOY_CHIP_FAMILY            — chip family, when [chip] is set
#   ALLOY_CHIP_DEVICE            — chip device, when [chip] is set
#   ALLOY_MANIFEST_JSON          — full manifest JSON for advanced callers
# ----------------------------------------------------------------------------
function(alloy_cli_init)
  cmake_parse_arguments(_ALLOY "" "PROJECT_DIR" "" ${ARGN})
  if(NOT _ALLOY_PROJECT_DIR)
    set(_ALLOY_PROJECT_DIR "${CMAKE_SOURCE_DIR}")
  endif()

  if(NOT Python3_EXECUTABLE)
    find_package(Python3 REQUIRED COMPONENTS Interpreter)
  endif()

  execute_process(
    COMMAND "${Python3_EXECUTABLE}" -m alloy_cli.cmake_bridge
            --project-dir "${_ALLOY_PROJECT_DIR}"
            --emit-json
    OUTPUT_VARIABLE _ALLOY_JSON
    ERROR_VARIABLE  _ALLOY_ERR
    RESULT_VARIABLE _ALLOY_RC
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )
  if(NOT _ALLOY_RC EQUAL 0)
    message(FATAL_ERROR
      "alloy_cli_init: failed to read alloy.toml from "
      "${_ALLOY_PROJECT_DIR}\n${_ALLOY_ERR}")
  endif()

  set(ALLOY_MANIFEST_JSON "${_ALLOY_JSON}" PARENT_SCOPE)

  string(JSON _NAME GET "${_ALLOY_JSON}" project name)
  set(ALLOY_PROJECT_NAME "${_NAME}" PARENT_SCOPE)

  string(JSON _ALLOY_VER ERROR_VARIABLE _ERR GET "${_ALLOY_JSON}" project alloy)
  if(NOT _ERR)
    set(ALLOY_PROJECT_ALLOY "${_ALLOY_VER}" PARENT_SCOPE)
  endif()

  string(JSON _CODEGEN_VER ERROR_VARIABLE _ERR GET "${_ALLOY_JSON}" project alloy-codegen)
  if(NOT _ERR)
    set(ALLOY_PROJECT_ALLOY_CODEGEN "${_CODEGEN_VER}" PARENT_SCOPE)
  endif()

  string(JSON _BOARD ERROR_VARIABLE _ERR GET "${_ALLOY_JSON}" board id)
  if(NOT _ERR)
    set(ALLOY_BOARD_ID "${_BOARD}" PARENT_SCOPE)
  else()
    string(JSON _VENDOR GET "${_ALLOY_JSON}" chip vendor)
    string(JSON _FAMILY GET "${_ALLOY_JSON}" chip family)
    string(JSON _DEVICE GET "${_ALLOY_JSON}" chip device)
    set(ALLOY_CHIP_VENDOR "${_VENDOR}" PARENT_SCOPE)
    set(ALLOY_CHIP_FAMILY "${_FAMILY}" PARENT_SCOPE)
    set(ALLOY_CHIP_DEVICE "${_DEVICE}" PARENT_SCOPE)
  endif()
endfunction()

# ----------------------------------------------------------------------------
# alloy_cli_resolve_alloy_tag(<output_var>)
#
# Resolves the GIT_TAG to pin the alloy HAL at.  Reads
# ``ALLOY_PROJECT_ALLOY`` (set by alloy_cli_init from
# alloy.toml [project].alloy) and falls back to ``main`` when no
# version is pinned.
# ----------------------------------------------------------------------------
function(alloy_cli_resolve_alloy_tag output_var)
  if(ALLOY_PROJECT_ALLOY)
    set(${output_var} "${ALLOY_PROJECT_ALLOY}" PARENT_SCOPE)
  else()
    set(${output_var} "main" PARENT_SCOPE)
  endif()
endfunction()

# ----------------------------------------------------------------------------
# alloy_cli_link(<target>)
#
# Wires the generated ``.alloy/generated/include`` directory into ``target``'s
# include path.  When the alloy HAL is also available (FetchContent /
# add_subdirectory / find_package), alloy_add_runtime_executable already
# linked it; we just layer the codegen output on top.  Projects that consume
# alloy-cli without alloy/ get a friendly warning instead of a hard error
# so existing CI configurations keep working through this transition.
# ----------------------------------------------------------------------------
function(alloy_cli_link target)
  if(NOT TARGET ${target})
    message(FATAL_ERROR "alloy_cli_link: '${target}' is not a CMake target.")
  endif()
  target_include_directories(${target} PRIVATE
    "${CMAKE_SOURCE_DIR}/.alloy/generated/include"
  )
  if(NOT TARGET Alloy::hal AND NOT _ALLOY_CLI_LINK_NO_HAL_WARNED)
    message(WARNING
      "alloy_cli_link: target Alloy::hal is missing.  Did the project's "
      "CMakeLists drop the FetchContent_Declare(alloy ...) block?  "
      "alloy_cli_link will only add the codegen include path.")
    set(_ALLOY_CLI_LINK_NO_HAL_WARNED TRUE PARENT_SCOPE)
  endif()
endfunction()
