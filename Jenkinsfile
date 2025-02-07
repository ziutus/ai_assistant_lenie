pipeline {
    agent any
    options {
        skipDefaultCheckout(true)
    }
    environment {
        INSTANCE_ID = "${params.INSTANCE_ID}" // Dla prostoty dostępu
        AWS_REGION = 'us-east-1'
    }

    stages {
         stage('Check and Start AWS Machine') {
             agent {
                label 'built-in' // Wymuszenie wykonania na "Built-In Node"
             }

            steps {
                script {
                        // Używaj parametru INSTANCE_ID przekazywanego do joba
                        def instanceID = env.INSTANCE_ID

                        echo "Using instance ID: ${instanceID}"

                        // Logika operacji AWS
                        def instanceState = sh(
                            script: """
                            aws ec2 describe-instances \
                                --instance-ids ${instanceID} \
                                --query "Reservations[0].Instances[0].State.Name" \
                                --output text \
                                --region ${env.AWS_REGION}
                            """,
                            returnStdout: true
                        ).trim()

                        echo "Current state of AWS instance ${instanceID}: ${instanceState}"

                        if (instanceState == "terminated") {
                            error "AWS instance ${instanceID} has been terminated. Cannot start it. Please recreate the instance."
                        } else if (instanceState != "running") {
                            echo "Starting AWS instance..."
                            sh """
                            aws ec2 start-instances --instance-ids ${instanceID} --region ${env.AWS_REGION}
                            """
                            sh """
                            aws ec2 wait instance-running --instance-ids ${instanceID} --region ${env.AWS_REGION}
                            """
                            echo "AWS instance ${instanceID} is now running."
                        } else {
                            echo "AWS instance ${instanceID} is already running."
                        }
                    }
                }
         }

         stage('Code checkout from GitHub') {
             agent {
                label 'aws-ec2-runner'
             }
            steps {
                script {
                    cleanWs()
                    git credentialsId: 'github-token', url: 'https://github.com/ziutus/ai_assistant_lenie_server', branch: 'main'
                }
            }
        }
        stage('Example') {
             agent {
                label 'aws-ec2-runner'
             }
            steps {
                echo 'Hello!'
                sh 'ls -la'
            }
        }
//         stage('Check file') {
//             steps {
//                 echo 'checking if file exist'
//                 sh 'ls -l passive_scan.yaml'
//             }
//         }
        stage('report dir creation') {
             agent {
                label 'aws-ec2-runner'
             }
            steps {
                echo 'create directory for reports'
                sh 'mkdir ${WORKSPACE}/results/'
            }
        }
        stage('check workspace') {
             agent {
                label 'aws-ec2-runner'
             }
            steps {
                echo 'checking if file exist'
                sh 'ls -l "$WORKSPACE"'
            }
        }

    stage('Run Pytest') {
        agent {
            label 'aws-ec2-runner' // Wskazanie runnera w Jenkins odpowiadającego GitLabowi (np. AWS)
        }
        steps {
            script {
                // Instalacja wymaganych zależności Python
                echo 'Installing requirements...'
                sh """
                pip install -r requirements.txt
                """

                // Tworzenie katalogu na wyniki jeżeli nie istnieje
                echo 'Ensuring results directory exists...'
                sh """
                mkdir -p pytest-results
                """

                // Uruchomienie testów i generacja raportu w HTML
                echo 'Running Pytest...'
                sh """
                pytest --self-contained-html --html=pytest-results/report.html || true
                """


            }

            // Zrzucenie katalogu wyników do logów Jenkins
            echo 'Archiving test results...'
            archiveArtifacts artifacts: 'pytest-results/**/*', allowEmptyArchive: true
        }
        post {
            always {
                echo 'Pytest stage completed. Results saved as artifacts.'
            }
        }
    }


        // stage('Semgrep Scan') {
        //     steps {
        //         echo 'Running Semgrep scan'
        //         sh """
        //             semgrep --config=auto --json --output /zap/wrk/results/semgrep-report.json
        //             """
        //     }
        // }


 //        stage('[OSV-Scanner] scan') {
	// 		steps {
	// 			sh '''
	// 			  osv-scanner scan --lockfile package-lock.json --output osv-scanner-output.txt || true
	// 			'''
	// 		}
	// }


 //        stage('[trufflehog] scan') {
	// 		steps {
	// 			sh '''
	// 				docker run --rm --name trufflehog  \
	// 					trufflesecurity/trufflehog:latest \
	// 					 git  file://. --only-verified --bare --json 2>trufflehog_errors.txt > /zap/wrk/results/trufflehog.json

	// 			'''
	// 			defectDojoPublisher(artifact: '/zap/wrk/results/trufflehog.json',
	// 			    productName: 'Juice Shop',
	// 			    scanType: 'Trufflehog Scan',
	// 			    engagementName: 'krzysztof@odkrywca.eu')

	// 		}
	// }




//          stage('[ZAP] Baseline passive-scan') {
// 			steps {
// 				sh '''
// 					docker run --name juice-shop -d \
// 						-p 3000:3000 \
// 						bkimminich/juice-shop
// 					sleep 5
// 				'''
// 				sh '''
// 					docker run --name zap  \
// 						--add-host=host.docker.internal:host-gateway \
// 						-v zap_config:/zap/wrk/:rw \
// 						-t ghcr.io/zaproxy/zaproxy:stable bash -c \
// 						"ls -l /zap/wrk/; zap.sh -cmd -addonupdate; zap.sh -cmd -addoninstall communityScripts -addoninstall pscanrulesAlpha -addoninstall pscanrulesBeta -autorun /zap/wrk/passive_scan.yaml" \
// 						|| true
// 				'''
// 			}
// 	    }
// 	    stage('Copy ZAP report') {
// 		    steps {
// 			sh '''
// 				docker run --rm -d -v zap_config:/app --name busybox busybox sh -c "sleep 4000"
// 		  		docker cp busybox:/app/reports/zap_xml_report.xml ${WORKSPACE}/results/zap_xml_report.xml
// 		 	'''
// 		    }
// 	    }

    }
//     post {
//         always {

//             sh '''
// 				ls -l /zap/wrk/passive_scan.yaml
// 				docker stop busybox
//             '''
		// docker stop trufflehog
		// defectDojoPublisher(artifact: '/zap/wrk/results/semgrep-report.json',
		//     productName: 'Juice Shop',
		//     scanType: 'Semgrep JSON Report',
		//     engagementName: 'krzysztof@odkrywca.eu')
//        }
//     }
    post {
        always {
            // Zatrzymywanie instancji EC2 po zakończeniu pipeline
            node('built-in') { // Wykonywane wyłącznie na "Built-In Node"
                script {
                    echo "Attempting to stop AWS EC2 instance..."
                    try {
                        sh """
                        aws ec2 stop-instances --instance-ids ${env.INSTANCE_ID} --region ${env.AWS_REGION}
                        """
                        sh """
                        aws ec2 wait instance-stopped --instance-ids ${env.INSTANCE_ID} --region ${env.AWS_REGION}
                        """
                        echo "AWS instance ${env.INSTANCE_ID} has been successfully stopped."
                    } catch (err) {
                        echo "Failed to stop AWS instance ${env.INSTANCE_ID}: ${err.getMessage()}"
                    }
                }
            }
        }
    }

}