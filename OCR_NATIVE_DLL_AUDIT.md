# OCR native-library audit

This is a traceability inventory for the private review preview. It is **not a redistribution clearance**.

- Extracted installer: [UB Mannheim Tesseract 5.5.3.20260724 for Windows](https://github.com/UB-Mannheim/tesseract/wiki), hosted under the upstream Tesseract 5.5.3 release.
- Installer SHA-256: `bee9e3434bd94fd65387d9be28cd467a41f61b1275383b55b0f59a1331270ae4`.
- The 55 DLLs below total 95,765,105 bytes. Each is an exact extracted file. Component package/version, license, copyright, source and redistribution notices still require verification.
- The extracted installer offers only `doc/LICENSE` and `doc/README.md` among files named for licenses/readmes; these do not establish all dependency notices.

| DLL | Bytes | SHA-256 |
| --- | ---: | --- |
| `libarchive-13.dll` | 972210 | `ddabddfdc98e1e1342ce4a7069fb4004de6c870d7bc9f4e95ef243dd18468e97` |
| `libb2-1.dll` | 34653 | `77bab532b5421d6cdddb96c3ae9a4bde144eb481ccaf243336c9f8c690a50987` |
| `libbrotlicommon.dll` | 143429 | `ca7bc06ead80259971badf2cd0bfc688db9154dad65f139f49a38b4be9976f97` |
| `libbrotlidec.dll` | 62461 | `a142dc6cfa77cb907028aa9426f486f3d8de37855e8db2ae2894147908121881` |
| `libbz2-1.dll` | 100964 | `b79cd3a7102e359ef6324e98966a67939e58ec2b651ae2847cae84a4dfa453f7` |
| `libcairo-2.dll` | 1247164 | `c474166543aed18b389b20122ca2741189504994dafd86cd5ed121e95bd82ce4` |
| `libcurl-4.dll` | 1226963 | `3d302f9690e810fdfd950254e2f0663d0ff768737f350c602a4ed3a06e9b6b2b` |
| `libdatrie-1.dll` | 35033 | `2f784872e6404e57847201fe1e7e591bd5b5be4a319ef38ebcb36014ac7f385d` |
| `libdeflate.dll` | 99228 | `3f3fc3a73bc3623dc93b37bb321c484d3731d93006fd01c0495d15711826eb44` |
| `libexpat-1.dll` | 237603 | `92ae866c6c58dd2d8366aa0e6230ba8d434d5306e8d8c3a08b7e61750fc16153` |
| `libffi-8.dll` | 40945 | `390e4bf8abd037abd0e1dd1f311606715e43f8efe812e5c5b8775acf2cb2f21e` |
| `libfontconfig-1.dll` | 502866 | `661c44249b9b06820554940a984b783b1daae9740a4a2eb265fe77205962486f` |
| `libfreetype-6.dll` | 790651 | `bbb3e6390ee229c867ef31f10e42a49a61a92e434a11d40c6139a2608ebc6194` |
| `libfribidi-0.dll` | 156403 | `84930fd86a3b46b62794a3bbaff21fbbaeaade5ff7cdc70be7f717ad29af87ed` |
| `libgcc_s_seh-1.dll` | 954773 | `172cfdc9d83703ec0a0ca2cee08f6cf2a166b801717ee51a56b3a63b36bc2f83` |
| `libgif-7.dll` | 45777 | `5b3d837ccaab84683dd93fbaddf2d98e1a9f90e0ddb8ea73dc70157adb4d26f1` |
| `libgio-2.0-0.dll` | 1915159 | `3dc3d4d477633cc9265b0796f9037a9fa387f4a1e8b7258890987a8c2c21eb0a` |
| `libglib-2.0-0.dll` | 1566649 | `43f2015fccfb10e22ecece61855d9ea21835f833b6533bc53ab77b54f4d66c34` |
| `libgmodule-2.0-0.dll` | 26748 | `69cf44cda7756a6ec4a926e0cf9fe81721f05d65abfab88ff83004fa508bb0e7` |
| `libgobject-2.0-0.dll` | 359475 | `acf20d5ddd3d2e4b4355576f5cf662c18f42746c50f43eaccc0596592616602a` |
| `libgraphite2.dll` | 167155 | `063a9ad34a5ec87d038b4646660957395224ecf2cf707917256b7d251a7c5f57` |
| `libharfbuzz-0.dll` | 1541957 | `54fb644a1143b3b81d494684f299aca9ff4b72134f12a7b1cfb2bd0f8fa9cef7` |
| `libiconv-2.dll` | 1143148 | `7a282a854e01be726c6cccfe46f548c716aa45b3014818468253aaa4efbcd067` |
| `libicudt78.dll` | 33120806 | `47d19b605a28461d44e0d8c062c465e92c9edfb0244f023a8066f7337d317d0e` |
| `libicuin78.dll` | 3186867 | `af3341827897a41ab16667ee0699acdb2b0338c3bf4ecc7f510a324f18755422` |
| `libicuuc78.dll` | 1999466 | `3186171e946552e2a5e371cd0bc68bf37bd6e229a85dbb0d3c40231cf0858b49` |
| `libidn2-0.dll` | 247081 | `9880b52651a0247640a2531d777380f7c35fac7efa7e3979b265ddcb78db8642` |
| `libintl-8.dll` | 298731 | `0537c3dd2378218508ebe3cc416d72a99ee2d24ae1c5525e23458f32544ef861` |
| `libjbig-0.dll` | 62083 | `275a827ba6839d47cfdbe059db1b1b403a92ff26e2b76a29362915487868bef2` |
| `libjpeg-8.dll` | 967968 | `b564d34adaca83e73af0e2231719dd0198ea6cd074c64b2ba85bfd7182f27db7` |
| `libleptonica-6.dll` | 2850600 | `1869b44e3d46fd830620b042477e5d60a950779582f38f60291547efb27792f1` |
| `libLerc.dll` | 804265 | `6887fb5aeabf382a835a4cb693025e8d48d9c90e82ca4eae5d2d8ffb70c6ca9a` |
| `liblz4.dll` | 158649 | `35f917274bca8f19677ba66f1b3cc3c83568c3249fc43215fc16e76439c8e856` |
| `liblzma-5.dll` | 191836 | `dc9edb9bd83b0371fe68d96cb3e70cd17b7a5aba958326a18f8210cb812432e9` |
| `libopenjp2-7.dll` | 519082 | `123587086cb1a25d2a338fb9b7c1d6bda10bf9062625b4f08c6a92b3d9cafe47` |
| `libpango-1.0-0.dll` | 437317 | `a7722692aa345f88cd0cb0296ad144e14b89a25c9926b5c3bac815331bba2127` |
| `libpangocairo-1.0-0.dll` | 84876 | `f0efa65511bc8f35186e9adf4628fb9ed505b31435a93afe218ae6c348197954` |
| `libpangoft2-1.0-0.dll` | 112015 | `adeeffc8438397998f449f8da1bd3832f4c031215415d7ed21109582dc6908a6` |
| `libpangowin32-1.0-0.dll` | 112948 | `08a8ac72c621158d47eb713139e0ad9021c43bef1af01f1365a41fb7f33272c8` |
| `libpcre2-8-0.dll` | 717955 | `a499fb8a7eff453d6e4f0842576bc5171d40a1505d8f7f13fff6cee51b738a62` |
| `libpixman-1-0.dll` | 740378 | `55ce45825eb8e825c635416171be4736147a6b0b690469f545d8c4ae8e85b4a3` |
| `libpng16-16.dll` | 264269 | `3737838ee8d6b893df7bdabf7439775371a57dce7e17ee6b35586023c64bd9ab` |
| `libpsl-5.dll` | 105304 | `b31fc70eda598a39b65fe2736d815518db0652d641346f75eac40c2a0499b058` |
| `libsharpyuv-0.dll` | 53757 | `ab0c9f61dc69b6bcdff1011e215f8d5fd6e5096aba9be3386ab87f217fbbeffe` |
| `libssh2-1.dll` | 271318 | `ee7fe3e749859334c99e9261689481dd879811122598d22585421f95d29fc7ae` |
| `libstdc++-6.dll` | 26390974 | `5fe5d4d8f6636eb6f2dc55be99dc5dc8a6c40db1abdf592e84480d1e6985abd0` |
| `libtesseract-5.dll` | 3501048 | `54d54528b453ce3a5ba79487687f8df43e7b194b9ea97beba74200453fe1fb46` |
| `libthai-0.dll` | 72294 | `5d741974fdec19e0f6cddbcdb539428af0c7392740a056634714c2884157fdb9` |
| `libtiff-6.dll` | 625178 | `47fe69165bf8e211aaa84224f51f145dc894e330fe7ca167f7c99419e0c8c894` |
| `libunistring-5.dll` | 2251328 | `b91e2850d3668d4931056a8f4d35783b8ec3eea3735485108a936a072cd16071` |
| `libwebp-7.dll` | 749724 | `c6c21a10f8cfe13270832e64640b82709e1d87b956b5f15af435a6c25acd6bbf` |
| `libwebpmux-3.dll` | 82858 | `2c8a2e9d7901ec65330f31f9989c2a07ef0506e903b485fcd8b241a6bab9b88f` |
| `libwinpthread-1.dll` | 65955 | `6a661d5846d80a91394dbb9b2dab87ba3cc705eac80ad45fe73677bff70cd6d2` |
| `libzstd.dll` | 1218273 | `b95c223a9548a9ecf51377c962e0bc8f0c51eb0c6f67a296dbc885996f0dd40d` |
| `zlib1.dll` | 128488 | `93e9243a44c29200eeacaf9658efe2558581770e4b11ca4b500e18e424a6e3b5` |

## Release gate

Map every file to its source package and exact version, capture required license and copyright text, and verify that those terms allow repacking in the application. Rebuild from pinned upstream source and registered dependencies when possible. The current OCR bundle must remain private review material.
