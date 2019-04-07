#
# Contains title and explanation of each possible movement (per exercise)
#
#   Format:
#
#       Exercise (A/B/C)
#
#           - Gesture 1
#               > Name
#               > Description (HTML)
#
#           - Gesture 2
#               > Name
#               > Description (HTML)
#               .
#               .
#           - Gesture N
#
#
MOVEMENT_DESC = {
                    "A": {
                            1: ("Index Finger Flexion", "<b>Simple</b>:<ul><li>Flex your index finger</ul>"),

                            2: ("Index Finger Extension", "<b>Simple</b>:<ul><li>Extend your index finger</ul>"),

                            3: ("Middle Finger Flexion", "<b>Simple</b>:<ul><li>Flex your middle finger</ul>"),

                            4: ("Middle Finger Extension", "<b>Simple</b>:<ul><li>Extend your middle finger</ul>"),

                            5: ("Ring Finger Flexion", "<b>Simple</b>:<ul><li>Flex your ring finger</ul>"),

                            6: ("Ring Finger Extension", "<b>Simple</b>:<ul><li>Extend your ring finger</ul>"),

                            7: ("Little Finger Flexion", "<b>Simple</b>:<ul><li>Flex your little finger</ul>"),

                            8: ("Little Finger Extension", "<b>Simple</b>:<ul><li>Extend your little finger</ul>"),

                            9: ("Thumb Adduction", "<b>Moderate Difficulty</b>:<ul><li>Move your thumb towards the palm of your hand</li><li>Keep your thumb in line with your index finger</li></ul>"),

                            10: ("Thumb Abduction", "<b>Moderate Difficulty</b>:<ul><li>Move your thumb away from the palm of your hand</li><li>Keep your thumb in line with your index finger</li></ul>"),

                            11: ("Thumb Flexion", "<b>Moderate Difficulty</b>:<ul><li>Move your thumb towards the base (bottom) of your middle finger</ul>"),

                            12: ("Thumb Extension", "<b>Moderate Difficulty</b>:<ul><li>Move your thumb away from your palm</li><li> Keep your thumb on the plane created by your palm</li></ul>"),
                    },

                    "B": {
                            1: ("Thumb Up", "<b>Simple</b>:<ul><li>Make a closed hand</li><li> Extend your thumb</li></ul>"),

                            2: ("Sign for Two", "<b>Moderate Difficulty</b>:<ul><li>Extend your index and middle finger</li><li>Flex the remaining fingers</li></ul>"),

                            3: ("Sign for Three", "<b>Moderate Difficulty</b>:<ul><li>Flex your ring and little finger</li><li> Extend the rest</li></ul>"),

                            4: ("Sign for Four", "<b>Moderate Difficulty</b>:<ul><li>Extend all fingers</li><li> Touch the base of your little finger with your thumb</li></ul>"),

                            5: ("Sign for Five", "<b>Simple</b>:<ul><li>Extend all fingers</ul>"),

                            6: ("Fist", "<b>Simple</b>:<ul><li>Make a fist</ul>"),

                            7: ("Pointing Gesture", "<b>Moderate Difficulty</b>:<ul><li>Make a fist</li><li> Point your index finger</li></ul>"),

                            8: ("Adduction of Extended Fingers", "<b>Difficult</b>:<ul><li>Start with all fingers extended</li><li>Bring your fingers together</li></ul>"),

                            9: ("Wrist Supination (Axis: Middle)", "<b>Moderate Difficulty</b>:<ul><li>Rotate your hand clockwise (along the middle finger axis)</ul>"),

                            10: ("Wrist Pronation (Axis: Middle)", "<b>Moderate Difficulty</b>:<ul><li>Rotate your hand counterclockwise (along the middle finger axis)</ul>"),

                            11: ("Wrist Supination (Axis: Little)", "<b>Moderate Difficulty</b>:<ul><li>Rotate your hand clockwise (along the little finger axis)</ul>"),

                            12: ("Wrist Pronation (Axis: Little)", "<b>Moderate Difficulty</b>:<ul><li>Rotate your hand counterclockwise (along the little finger axis)</ul>"),

                            13: ("Wrist Flexion", "<b>Simple</b>:<ul><li>Have your fingers drawn together</li><li>Flex your wrist</li></ul>"),

                            14: ("Wrist Extension", "<b>Simple</b>:<ul><li>Have your fingers drawn together</li><li>Extend your wrist</li></ul>"),

                            15: ("Wrist Radial Deviation", "<b>Simple</b>:<ul><li>Rotate your wrist clockwise</ul>"),

                            16: ("Wrist Ulnar Deviation", "<b>Simple</b>:<ul><li>Rotate your wrist counterclockwise</ul>"),

                            17: ("Wrist Extension & Closed Hand", "<b>Moderate Difficulty</b>:<ul><li>Make a closed hand</li><li>Extend your wrist</li></ul>"),
                    },

                    "C": {
                            1: ("Large Diameter Grasp", "<b>Simple</b>:<ul><li>Grasp an object of large diameter, that you cannot fully grasp</ul>"),

                            2: ("Small Diameter Grasp", "<b>Simple</b>:<ul><li>Grasp an object of small diameter</li><li>Use a powerful grasp</li></ul>"),

                            3: ("Fixed Hook Grasp", "<b>Simple</b>:<ul><li>Grasp an object of medium diameter</li><li>Keep thumb extended</li></ul>"),

                            4: ("Index Finger Extension Grasp", "<b>Moderate Difficulty</b>:<ul><li>Place index finger on top of blade</li><li>Place thumb on side of blade</li></ul>"),

                            5: ("Medium Wrap", "<b>Simple</b>:<ul><li>Grasp an object of medium diameter</li><li>Your thumb and index should meet</li></ul>"),

                            6: ("Ring Grasp", "<b>Simple</b>:<ul><li>Grab an object using only your thumb and index</ul>"),

                            7: ("(Prismatic) Four Finger Grasp", "<b>Moderate Difficulty</b>:<ul><li>Grab an object of very small diameter</li><li>Use only the tips of your fingers and thumb</li></ul>"),

                            8: ("Stick Grasp", "<b>Moderate Difficulty</b>:<ul><li>Grab an object of very small diameter</li>"
                                               "<li>Wrap your fingers around the object and place the tips of your fingers on the object</li>"
                                               "<li>Your thumb should oppose the object</li></ul>"),

                            9: ("(Writing) Tripod Grasp", "<b>Simple</b>:<ul><li>Grasp an object of smal diameter</li><li>Use only your index and middle fingers, along with your thumb</li></ul>"),

                            10: ("Power Sphere Grasp", "<b>Simple</b>:<ul><li>Grasp a spherical object</li><li>Wrap fingers around the object and use a powerful grasp</li></ul>"),

                            11: ("Three Finger Sphere Grasp", "<b>Simple</b>:<ul><li>Grasp a spherical object</li><li>Use all fingers but the little finger</li></ul>"),

                            12: ("Precision Sphere Grasp", "<b>Simple</b>:<ul><li>Grasp a spherical object</li><li>Use only the tips of your fingers</li></ul>"),

                            13: ("Tripod Grasp", "<b>Simple</b>:<ul><li>Grasp a spherical object</li><li>Use only your thumb, index and middle fingers</li></ul>"),

                            14: ("(Prismatic) Pinch Grasp", "<b>Moderate Difficulty</b>:<ul><li>Pick up a tiny object with a pinch grip</li><li>Extend middle, ring and little fingers back</li></ul>"),

                            15: ("Tip Pinch Grasp", "<b>Moderate Difficulty</b>:<ul><li>Pick up a tiny object with a pinch grip</li><li>Do not extend fingers away from pinch grip</li></ul>"),

                            16: ("Quadpod Grasp", "<b>Simple</b>:<ul><li>Pick up a small object using only the tips of fingers</li><li>Do not use the little finger</li></ul>"),

                            17: ("Lateral Grasp", "<b>Moderate Difficulty</b>:<ul><li>Make a closed hand</li><li>Place an object between the thumb and index finger</li>"
                                                  "<li>Raise object while keep object level with arm</li></ul>"),

                            18: ("Parallel Extension Grasp", "<b>Simple</b>:<ul><li>Pick an object from above</li><li>Clamp, such that the object is perpendicular to the arm</li></ul>"),

                            19: ("Extension Type Grasp", "<b>Simple</b>:<ul><li>Place fingers below an object, and thumb on top</li><li>Pick up the object</li></ul>"),

                            20: ("Power Disk Grasp", "<b>Simple</b>:<ul><li>Grab a disc-like object with a powerful grasp</li></ul>"),

                            21: ("Open Bottle (Tripod Grasp)", "<b>Simple</b>:<ul><li>Open a bottle by the cap from above</li><li>Use only thumb, index and middle finger</li></ul>"),

                            22: ("Turn Screwdriver (Stick Grasp)", "<b>Difficult</b>:<ul><li>Wrap fingers around a screwdriver, and flex fingers on the screwdriver</li>"
                                                                   "<li>Have thumb opposed to the screwdriber</li>"
                                                                   "<li>Point the screwdriver downwards and rotate clockwise</li></ul>"),

                            23: ("Cut Object (Index Grasp)", "<b>Moderate Difficulty</b>:<ul><li>Place index finger on top of blade</li>"
                                                             "<li>Place thumb on the side of the blade</li>"
                                                             "<li>Apply pressure on the blade and move backwards</li></ul>"),

                    }
                }
