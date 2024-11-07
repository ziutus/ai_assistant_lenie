pipeline {
    agent any
    options {
        skipDefaultCheckout(true)
    }
    stages {
         stage('Code checkout from GitHub') {
            steps {
                script {
                    cleanWs()
                    git credentialsId: 'github-token', url: 'https://github.com/ziutus/ai_assistant_lenie_server', branch: 'main'
                }
            }
        }
        stage('Example') {
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
            steps {
                echo 'create directory for reports'
                sh 'mkdir ${WORKSPACE}/results/'
            }
        }
        stage('check workspace') {
            steps {
                echo 'checking if file exist'
                sh 'ls -l "$WORKSPACE"'
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
}