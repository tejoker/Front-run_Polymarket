use std::env;
use std::path::Path;

fn main() {
    println!("cargo:rerun-if-changed=src/polymarket_core.cpp");
    
    // Compiler le code C++
    let out_dir = env::var("OUT_DIR").unwrap();
    let src_dir = "src";
    
    // Compiler en objet
    let status = std::process::Command::new("g++")
        .args(&[
            "-std=c++17",
            "-c",
            "-fPIC",
            "-o", &format!("{}/polymarket_core.o", out_dir),
            &format!("{}/polymarket_core.cpp", src_dir)
        ])
        .status()
        .expect("Failed to compile C++ object");
    
    if !status.success() {
        panic!("Failed to compile C++ object");
    }
    
    // Créer la bibliothèque dynamique
    let status = std::process::Command::new("g++")
        .args(&[
            "-shared",
            "-o", &format!("{}/libpolymarket_core.dylib", out_dir),
            &format!("{}/polymarket_core.o", out_dir),
            "-lcurl",
            "-lsqlite3"
        ])
        .status()
        .expect("Failed to create dynamic library");
    
    if !status.success() {
        panic!("Failed to create dynamic library");
    }
    
    // Dire à Rust où trouver la bibliothèque
    println!("cargo:rustc-link-search=native={}", out_dir);
    println!("cargo:rustc-link-lib=dylib=polymarket_core");
    println!("cargo:rustc-link-lib=dylib=curl");
    println!("cargo:rustc-link-lib=dylib=sqlite3");
}
